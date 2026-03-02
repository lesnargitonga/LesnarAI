"""
UNet model definition for semantic segmentation (TensorFlow / Keras)

Supports binary or multi-class segmentation based on num_classes.
"""

from typing import Tuple
import tensorflow as tf
import keras
from keras import layers


def conv_block(x, filters: int, kernel_size: int = 3, activation: str = "relu"):
    x = layers.Conv2D(filters, kernel_size, padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation(activation)(x)
    x = layers.Conv2D(filters, kernel_size, padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation(activation)(x)
    return x


def encoder_block(x, filters: int):
    x = conv_block(x, filters)
    p = layers.MaxPooling2D((2, 2))(x)
    return x, p


def decoder_block(x, skip, filters: int):
    x = layers.Conv2DTranspose(filters, (2, 2), strides=2, padding="same")(x)
    x = layers.Concatenate()([x, skip])
    x = conv_block(x, filters)
    return x


def build_unet(
    input_shape: Tuple[int, int, int] = (256, 256, 3),
    num_classes: int = 1,
    base_filters: int = 64,
):
    inputs = keras.Input(shape=input_shape)

    # Encoder
    s1, p1 = encoder_block(inputs, base_filters)
    s2, p2 = encoder_block(p1, base_filters * 2)
    s3, p3 = encoder_block(p2, base_filters * 4)
    s4, p4 = encoder_block(p3, base_filters * 8)

    # Bridge
    b = conv_block(p4, base_filters * 16)

    # Decoder
    d1 = decoder_block(b, s4, base_filters * 8)
    d2 = decoder_block(d1, s3, base_filters * 4)
    d3 = decoder_block(d2, s2, base_filters * 2)
    d4 = decoder_block(d3, s1, base_filters)

    # Output
    if num_classes == 1:
        activation = "sigmoid"
        channels = 1
    else:
        activation = "softmax"
        channels = num_classes

    outputs = layers.Conv2D(channels, 1, padding="same", activation=activation)(d4)

    model = keras.Model(inputs, outputs, name=f"unet_{num_classes}cls")
    return model


__all__ = ["build_unet"]
