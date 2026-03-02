import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import gymnasium as gym
from gymnasium import spaces
from sb3_contrib import RecurrentPPO
from sb3_contrib.common.recurrent.type_aliases import RNNStates
from stable_baselines3.common.utils import get_device
import argparse
from pathlib import Path


class DummyMultiInputEnv(gym.Env):
    def __init__(self, img_h: int, img_w: int, kin_dim: int = 19):
        super().__init__()
        self.observation_space = spaces.Dict(
            {
                "visual": spaces.Box(low=0.0, high=1.0, shape=(1, img_h, img_w), dtype=np.float32),
                "kinematics": spaces.Box(low=-np.inf, high=np.inf, shape=(kin_dim,), dtype=np.float32),
            }
        )
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(4,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        obs = {
            "visual": np.zeros(self.observation_space["visual"].shape, dtype=np.float32),
            "kinematics": np.zeros(self.observation_space["kinematics"].shape, dtype=np.float32),
        }
        return obs, {}

    def step(self, action):
        obs, info = self.reset()
        return obs, 0.0, True, False, info

# Custom Dataset
class ExpertDataset(Dataset):
    def __init__(self, npz_path):
        data = np.load(npz_path)
        # (N, H, W) -> (N, 1, H, W) for CNN
        self.visual = torch.tensor(data['visual'], dtype=torch.float32).unsqueeze(1) 
        self.kinematics = torch.tensor(data['kinematics'], dtype=torch.float32)
        self.actions = torch.tensor(data['actions'], dtype=torch.float32)
        
    def __len__(self):
        return len(self.actions)
    
    def __getitem__(self, idx):
        return {
            'visual': self.visual[idx],
            'kinematics': self.kinematics[idx]
        }, self.actions[idx]

def pretrain(args):
    # 1. Load Data
    print(f"Loading expert data from {args.data}...")
    dataset = ExpertDataset(args.data)
    # 90/10 Split
    train_size = int(0.9 * len(dataset))
    val_size = len(dataset) - train_size
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch)
    
    # 2. Init Model (Student)
    print("Initializing RecurrentPPO agent...")
    # Dummy env to initialize policy shapes (no AirSim needed for BC training)
    img_h = int(dataset.visual.shape[-2])
    img_w = int(dataset.visual.shape[-1])
    env = DummyMultiInputEnv(img_h=img_h, img_w=img_w, kin_dim=int(dataset.kinematics.shape[-1]))
    model = RecurrentPPO(
        "MultiInputLstmPolicy",
        env,
        verbose=1,
        learning_rate=args.lr,
        ent_coef=0.0, # No exploration in BC
        seed=42
    )
    
    device = get_device("auto")
    policy = model.policy.to(device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()
    
    best_val_loss = float('inf')
    
    print(f"Starting Behavior Cloning for {args.epochs} epochs...")
    
    for epoch in range(args.epochs):
        policy.train()
        train_loss = 0.0
        
        for obs_dict, target_action in train_loader:
            # Move to device
            obs = {k: v.to(device) for k, v in obs_dict.items()}
            target = target_action.to(device)
            
            optimizer.zero_grad()
            
            # Forward pass through policy
            # Note: SB3 RecurrentPolicy expects (obs, lstm_states, episode_starts)
            # For BC, we can assume stateless (lstm_states=None, episode_starts=None) 
            # OR ideally we should preserve sequences. 
            # Simplification: We treat each step as independent for "Reflex" cloning first.
            # To do this correctly with LSTM, we'd need sequential sampling.
            # However, SB3's forward() can accept single steps if we don't pass states.
            # Actually, `policy.get_distribution(obs)` is what we want? No, that samples.
            
            # Extract features then head
            features = policy.extract_features(obs)
            # If LSTM, we need to pass through it?
            # SB3 LstmPolicy:
            #   latent_pi, _ = self._process_sequence(features, lstm_states, episode_starts)
            #   distribution = self._get_action_dist_from_latent(latent_pi)
            
            # HACK: Using `evaluate_actions` is tricky because it computes log_prob, not MSE actions.
            # We want the MEAN of the distribution to match target.
            
            # Let's assume for BC we just want to match the output of the policy head.
            # But the policy has an LSTM...
            # If we ignore the LSTM state (pass zeros), we are training it to be reactive.
            # That is an okay starting point.
            
            # Create dummy states
            # batch_size = target.shape[0]
            # lstm_states = (torch.zeros(1, batch_size, policy.lstm_hidden_size).to(device), ...)
            # ... this is getting complex for a quick script.
            
            # Plan B: Just use the policy's `get_distribution`? 
            # The input to the LSTM layer expects sequence length dimension?
            # SB3 Recurrent forward() handles scaling.
            
            # Let's rely on the fact that we can call it.
            # But wait, `extract_features` returns (Batch, FeatDim).
            # `_process_sequence` expects (Batch, Seq, Feat).
            # We treat Seq=1.
            
            # Reshape features to (Batch, 1, Feat)
            # Wait, `extract_features` output layout depends on policy.
            
            # Let's try the high-level API `predict_values`? No.
            
            # Correct path for SB3 Recurrent:
            # 1. features = policy.extract_features(obs)
            # 2. latent_pi, latent_vf, lstm_states = policy.lstm_actor_critic(features, states, starts)
            # 3. mean_actions = policy.action_net(latent_pi)
            
            # We need dummy states.
            n_envs = target.shape[0] # Using batch size as n_envs
            # States: (num_layers, batch, hidden)
            # Just use None? SB3 usually initializes if None.
            
            # Actually, let's look at `policy.forward`
            # behavior_cloning_loss needs deterministic output (mean).
            
            features = policy.extract_features(obs)
            # Features: (Batch, Dim)
            # Add Sequence Dim: (Batch, Seq=1, Dim) ?
            # SB3 uses (Seq, Batch, Dim) or (Batch, Seq, Dim)?
            # It usually infers from episode_starts.
            
            # Recurrent policies require explicit LSTM states and episode starts.
            # For BC, we treat each batch as independent one-step episodes.
            n_envs = int(target.shape[0])
            episode_starts = torch.ones((n_envs,), dtype=torch.float32, device=device)

            # sb3-contrib recurrent policies expect RNNStates with separate (h, c) for actor and critic.
            n_layers = int(getattr(policy.lstm_actor, "num_layers", 1))
            hidden = int(getattr(policy.lstm_actor, "hidden_size", 256))
            h_pi = torch.zeros((n_layers, n_envs, hidden), device=device)
            c_pi = torch.zeros((n_layers, n_envs, hidden), device=device)
            h_vf = torch.zeros((n_layers, n_envs, hidden), device=device)
            c_vf = torch.zeros((n_layers, n_envs, hidden), device=device)
            lstm_states = RNNStates(pi=(h_pi, c_pi), vf=(h_vf, c_vf))

            pred_actions, _, _, _ = policy.forward(obs, lstm_states, episode_starts, deterministic=True)
            
            loss = loss_fn(pred_actions, target)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            
        avg_train = train_loss / len(train_loader)
        
        # Val
        policy.eval()
        val_loss = 0.0
        with torch.no_grad():
            for obs_dict, target_action in val_loader:
                obs = {k: v.to(device) for k, v in obs_dict.items()}
                target = target_action.to(device)
                n_envs = int(target.shape[0])
                episode_starts = torch.ones((n_envs,), dtype=torch.float32, device=device)

                n_layers = int(getattr(policy.lstm_actor, "num_layers", 1))
                hidden = int(getattr(policy.lstm_actor, "hidden_size", 256))
                h_pi = torch.zeros((n_layers, n_envs, hidden), device=device)
                c_pi = torch.zeros((n_layers, n_envs, hidden), device=device)
                h_vf = torch.zeros((n_layers, n_envs, hidden), device=device)
                c_vf = torch.zeros((n_layers, n_envs, hidden), device=device)
                lstm_states = RNNStates(pi=(h_pi, c_pi), vf=(h_vf, c_vf))

                pred_actions, _, _, _ = policy.forward(obs, lstm_states, episode_starts, deterministic=True)
                val_loss += loss_fn(pred_actions, target).item()
        
        avg_val = val_loss / len(val_loader)
        print(f"Epoch {epoch+1}/{args.epochs} | Train Loss: {avg_train:.4f} | Val Loss: {avg_val:.4f}")
        
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            print(f"  > Saving new best model to {args.save_path}")
            model.save(args.save_path)
            
    print("BC Pre-training Complete.")
    
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, default='expert_data.npz')
    parser.add_argument('--save_path', type=str, default='runs/ppo_lesnar_bc')
    parser.add_argument('--epochs', type=int, default=10)
    parser.add_argument('--batch', type=int, default=64)
    parser.add_argument('--lr', type=float, default=3e-4) # Standard PPO LR
    args = parser.parse_args()
    
    pretrain(args)

if __name__ == "__main__":
    main()
