# Partially authored by ChatGPT

import tensorflow as tf

(x_train, y_train), (x_test, y_test) = \
    tf.keras.datasets.cifar10.load_data()

x_train = x_train.astype("float32") / 255.0
x_test = x_test.astype("float32") / 255.0

model = tf.keras.applications.ResNet50(
    include_top=True,
    weights=None,      # <-- train from scratch
    classes=10,
    input_shape=(32, 32, 3)
)

model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

model.fit(
    x_train[:100],
    y_train[:100],
    epochs=10,
    validation_data=(x_test[:100], y_test[:100])
)

model.save("/output/resnet50.keras")
