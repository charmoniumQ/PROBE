import multiprocessing
import threading

if __name__ == "__main__":
    thread = threading.Thread(target=print, args=("hello from thread",))
    thread.start()
    proc = multiprocessing.Process(target=print, args=("hello from proc",))
    proc.start()
    proc.join()
    thread.join()
    print("done")
