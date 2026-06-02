import os
import cv2
import sys
print('PYTHON EXE:', sys.executable)
print('OS CPU count:', os.cpu_count())
try:
    print('CV2 threads:', cv2.getNumThreads())
except Exception as e:
    print('CV2 threads: error', e)
print('Environment thread vars:')
for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
    print(' ', k, '=', os.environ.get(k))
try:
    import tensorflow as tf
    print('TensorFlow available')
    try:
        print('TF intra:', tf.config.threading.get_intra_op_parallelism_threads())
        print('TF inter:', tf.config.threading.get_inter_op_parallelism_threads())
    except Exception as e:
        print('TF threading query error:', e)
except Exception as e:
    print('TensorFlow not available:', e)
