import sys


def dynamic_token_scheduling_dp(token_compute_times, C, d, verbose=False):
    N = len(token_compute_times)
    T_ready = [0.0] * N
    DP = [0.0] * N
    P = [0] * N
    for i in range(N):
        best = sys.float_info.max
        for j in range(i + 1):
            batch_size = i - j + 1
            current = (DP[j - 1] if j > 0 else 0.0) + C + batch_size * d
            if current < best:
                best = current
                P[i] = j
        DP[i] = best
    batches = []
    batches.reverse()
    return batches, DP[-1] if DP else 0.0
