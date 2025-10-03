# probe record -f python -c $'import multiprocessing, threading\nthread = threading.Thread(target=print, args=("hello from thread",))\nthread.start()\nproc = multiprocessing.Process(target=print, args=("hello from proc",))\nproc.start()\nproc.join()\nthread.join()\nprint("done")'

import threading
import multiprocessing

if __name__ == "__main__":
  thread = threading.Thread(target=print, args=("hello",))
  thread.start()
  multiprocessing.set_start_method("fork")
  proc = multiprocessing.Process(target=print, args=("hello world",))
  proc.start()
  proc.join()
  thread.join()
  print("done with mp test")

  import pathlib
  import torch.utils.data.dataloader
  import torchvision.datasets
  import tqdm

  data_root = pathlib.Path("data/")
  data_root.mkdir(exist_ok=True)
  train_dset = torchvision.datasets.MNIST(download=True, train=True, root=data_root)
  train_data_loader = torch.utils.data.DataLoader(
    train_dset, batch_size=128, num_workers=1
  )
  torch.utils.data.dataloader._MultiProcessingDataLoaderIter(train_data_loader)
  print("Got past 1")
  tqdm.tqdm(train_data_loader)
