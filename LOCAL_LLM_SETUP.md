# Local LLM Setup Guide

This guide explains how to run Rambling Rhino with a local LLM instead of the Groq API.

## Quick Start with Ollama

### 1. Install Ollama
Download and install Ollama from [https://ollama.ai](https://ollama.ai)

### 2. Pull a Model
Open a terminal and run:
```bash
ollama pull llama2
```

Recommended models:
- `llama2` - Good balance of speed and quality (7B or 13B)
- `mistral` - Faster, good for faster generation
- `neural-chat` - Chat-optimized, good narrative quality
- `dolphin-mixtral` - High quality (requires more VRAM)
- `openchat` - Fast and capable

### 3. Start Ollama Server
```bash
ollama serve
```

This starts Ollama on `http://localhost:11434` (the default).

### 4. Run Rambling Rhino with Local LLM
In another terminal, run:

```bash
# Basic run with default llama2 model
python main_system_script.py --local-llm

# Use a specific model
python main_system_script.py --local-llm --local-model mistral

# With custom settings
python main_system_script.py --local-llm --local-model dolphin-mixtral --events 20 --interactive

# Generate and save story
python main_system_script.py --local-llm --local-model llama2 --output-dir ./output
```

## Usage Examples

### Generate a story with local LLM
```bash
python main_system_script.py --local-llm
```

### Interactive game with local LLM
```bash
python main_system_script.py --local-llm --interactive
```

### Custom prompt with local LLM
```bash
python main_system_script.py --local-llm \
  --premise "A detective discovers a hidden society in the city's underground tunnels" \
  --genre "noir mystery"
```

### More events, more reflection (slower but better quality)
```bash
python main_system_script.py --local-llm \
  --local-model mistral \
  --events 50 \
  --reflection-passes 3
```

## Model Selection Guide

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| mistral | 7B | ⚡⚡⚡ | ⭐⭐ | Fast prototyping |
| llama2 | 7-13B | ⚡⚡ | ⭐⭐⭐ | Balanced (recommended) |
| neural-chat | 7B | ⚡⚡ | ⭐⭐⭐ | Narrative generation |
| dolphin-mixtral | 46B | ⚡ | ⭐⭐⭐⭐ | Best quality (needs 24GB+ VRAM) |
| openchat | 3.5B | ⚡⚡⚡ | ⭐⭐ | Resource-constrained |

## Troubleshooting

### "Cannot connect to local LLM"
- Make sure Ollama is running: `ollama serve`
- Check that port 11434 is available
- On macOS: Look for Ollama in the menu bar
- On Linux: Check if ollama service is running: `systemctl status ollama`

### "Model not found"
- Pull the model first: `ollama pull llama2`
- List available models: `ollama list`

### Slow generation
- Use a smaller model: `--local-model mistral`
- Reduce events: `--events 20`
- GPU support improves speed significantly

### Out of memory
- Use a smaller model
- Reduce `--events` parameter
- Close other applications
- Check available VRAM: `ollama ps`

## Performance Notes

- First run downloads and loads the model (~2-10 GB depending on model)
- Subsequent runs are faster as the model stays in memory
- Generation time varies: 7B models ~30s-2min per call, 13B+ models ~1-5min
- Local LLM runs entirely offline - no API costs or rate limits

## Comparing API vs Local

| Feature | Groq API | Local LLM |
|---------|----------|-----------|
| Speed | ⚡⚡⚡ Fast | ⚡ Variable |
| Cost | Free tier (rate limited) | $0 (compute costs) |
| Privacy | Sent to API | Stays local |
| Offline | ❌ No | ✅ Yes |
| Setup | API key only | Install + download model |
| Latency | Network-dependent | CPU/GPU-dependent |

## Advanced Configuration

To use a different Ollama instance:
```bash
# Modify LLMClient initialization if needed
# Default: http://localhost:11434
```

To adjust model parameters, you can manually modify `llm_api_wrapper.py`:
- `temperature`: 0.0-1.0 (lower = more deterministic)
- `max_tokens`: Adjust output length

## Getting Help

- Ollama docs: https://github.com/ollama/ollama
- Model library: https://ollama.ai/library
- GitHub issues: Check the Rambling Rhino repository
