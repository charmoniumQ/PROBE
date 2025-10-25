CLONE_TAG=1.0

caffe:
	git clone -b $(CLONE_TAG) --depth 1 https://github.com/BVLC/caffe.git .
	pip install --upgrade pip
	pip install --requirements caffe/python/requirements.txt pydot
	mkdir caffe/build
	cmake -DCPU_ONLY=1 -B build -S caffe/build
	cmake --build build
	env --chdir=caffe/data/mnist ./get_mnist.sh
	env --chdir=caffe/examples/mnist ./create_mnist.sh

vae_tutorial:
	git clone https://github.com/cdoersch/vae_tutorial.git
	env --chdir vae_tutorial PYTHONPATH=$PWD/caffe/python python mnist_vae.py

