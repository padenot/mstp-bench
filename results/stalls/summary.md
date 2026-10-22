| Arm | Recorded audio intact | Recording timeline intact | Catch-up after 500 ms stall, ms | Backlog before stalls (p95), ms | Source → playback before stalls, ms | Failed trials |
|---|---|---|---|---|---|---|
| firefox-audioworklet-128 | 3/3 | 3/3 | 1, 1, 1 | 16–20 | 83–87 | 0 |
| firefox-audioworklet-512 | 3/3 | 3/3 | 0, 1, 1 | 23–28 | 97–104 | 0 |
| firefox-worker-128 | 3/3 | 3/3 | 2, 2, 2 | 9–15 | 76–83 | 0 |
| chrome-audioworklet-128 | 0/3 | 0/3 | never, never, never | 27–32 | 119–133 | 0 |
| chrome-audioworklet-512 | 0/3 | 0/3 | never, never, never | 22–27 | 115–127 | 0 |
| chrome-worker-128 | 3/3 | 0/3 | never, never, never | 9–15 | 99–118 | 0 |
| chrome-mstp-128 | 3/3 | 0/3 | 1, 1, 1 | 5–6 | 81–90 | 0 |
