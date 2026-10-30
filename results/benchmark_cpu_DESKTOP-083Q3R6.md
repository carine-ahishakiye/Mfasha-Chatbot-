# Latency benchmark: cpu_DESKTOP-083Q3R6

## Environment

- os: Windows 10
- python: 3.13.3
- cpu: Intel64 Family 6 Model 78 Stepping 3, GenuineIntel
- machine: DESKTOP-083Q3R6
- torch: 2.15.0+cpu
- cuda_available: False
- model load time: app 156.3 s, speaker 7.2 s
- typed questions: 50, voice clips: 6, warm-up runs discarded: 3
- outcomes of typed questions: {'answered': 49, 'referred': 1, 'empty': 0}

## Response time (milliseconds)

| Stage | n | mean | median | p95 | max |
|---|---:|---:|---:|---:|---:|
| 3. Text preprocessing | 50 | 14.8 | 1.2 | 91.2 | 340.6 |
| 5. Retrieval and ranking | 50 | 13098.5 | 3390.0 | 58189.0 | 117838.4 |
| 2. Speech-to-text | 6 | 169592.5 | 176047.6 | 192743.1 | 192743.1 |
| 7. Text-to-speech | 50 | 47319.7 | 40843.1 | 108139.9 | 138023.5 |
| End to end, typed question (text answer) | 50 | 8099.2 | 1291.7 | 28431.7 | 92818.4 |
| End to end, typed question + spoken answer | 50 | 55418.9 | 42224.9 | 124836.4 | 170715.5 |
| End to end, voice question + spoken answer | 6 | 539758.0 | 267557.2 | 1944461.6 | 1944461.6 |
