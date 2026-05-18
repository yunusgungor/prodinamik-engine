# Quickstart

## 1. Create a run

```bash
prodinamik run software "Implement FFT algorithm"
```

Output:
```
✅ Run created: implement-fft-algorithm (software profile)
   State: spec
   Next: prototyping → iteration → review → release
```

## 2. List runs

```bash
prodinamik list
```

## 3. Transition state

```bash
prodinamik transition implement-fft-algorithm prototyping
```

## 4. View run details

```bash
prodinamik debug implement-fft-algorithm
```

## 5. Use the interactive shell

```bash
prodinamik shell
```

Inside the shell:

```
Prodinamik> list
Prodinamik> transition implement-fft-algorithm review
Prodinamik> debug implement-fft-algorithm
Prodinamik> help
Prodinamik> exit
```

## 6. Start the HTTP server

```bash
# Create an API key first
prodinamik auth create admin-bot --role admin

# Save the key that is printed! It will not be shown again.
# Output: Key created: admin-bot-a1b2c3d4
# Key: pdmk_<48 hex chars>

# Start server
prodinamik serve --port 8080

# In another terminal:
curl http://localhost:8080/healthz
curl -H "X-API-Key: pdmk_..." http://localhost:8080/api/v1/runs
```

## 7. Chaos engineering

```bash
# List available scenarios
prodinamik chaos list

# Run a safe scenario
prodinamik chaos run cpu-spike --duration 2

# View report
prodinamik chaos report
```
