import tensorflow as tf
import matplotlib.pyplot as plt
import argparse

import sys
import pathlib
root = pathlib.Path(__file__).resolve().parent.resolve()
sys.path.insert(0, str(root))
import components

parser = argparse.ArgumentParser()
parser.add_argument('--data-dir', default='/output')
args = parser.parse_args()

train_batches = tf.data.Dataset.load(args.data_dir + '/train_batches')
val_batches = tf.data.Dataset.load(args.data_dir + '/val_batches')

pos_encoding = components.positional_encoding(length=2048, depth=512)

# Check the shape.
print(pos_encoding.shape)

# Plot the dimensions.
plt.pcolormesh(pos_encoding.numpy().T, cmap='RdBu')
plt.ylabel('Depth')
plt.xlabel('Position')
plt.colorbar()
plt.savefig("position_encoding.png")

#@title
pos_encoding/=tf.norm(pos_encoding, axis=1, keepdims=True)
p = pos_encoding[1000]
dots = tf.einsum('pd,d -> p', pos_encoding, p)
plt.subplot(2,1,1)
plt.plot(dots)
plt.ylim([0,1])
plt.plot([950, 950, float('nan'), 1050, 1050],
         [0,1,float('nan'),0,1], color='k', label='Zoom')
plt.legend()
plt.subplot(2,1,2)
plt.plot(dots)
plt.xlim([950, 1050])
plt.ylim([0,1])
plt.savefig(args.data_dir + "/dots.png")
