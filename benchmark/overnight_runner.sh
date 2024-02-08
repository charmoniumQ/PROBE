set +e

for iters in $(seq 5); do
    for try in $(seq 3); do
        echo "Trying iters=$iters try=$try at $(date)" >> log
        ./result/bin/python runner.py --collectors working --iterations $iters --workloads working --stats performance
        if [ "$?" = 0 ]; then
           break
        fi
        echo "taking a short nap"
        sleep 15
    done
done
