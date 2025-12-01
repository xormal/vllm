# OpenAI Responses API Compliance Checker

Automated tool for checking vLLM server compliance with OpenAI Responses API specification.

## Features

- ✅ **Endpoint Testing**: Tests all Responses API endpoints via HTTP
- ✅ **Parameter Validation**: Validates request/response parameters
- ✅ **Streaming Events**: Tests SSE streaming events
- ✅ **Compliance Scoring**: Generates detailed compliance reports
- ✅ **Remote Testing**: Connects to remote vLLM servers
- ✅ **CI/CD Integration**: Can be integrated into automated pipelines

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to configure your server:

```yaml
server:
  base_url: "http://192.168.228.43:8000"
  api_version: "v1"
```

## Usage

### Quick Check

Run all compliance checks:

```bash
python check_compliance.py
```

### Specific Checks

Check only endpoints:
```bash
python check_compliance.py --endpoints-only
```

Check only streaming events:
```bash
python check_compliance.py --streaming-only
```

Check only parameters:
```bash
python check_compliance.py --parameters-only
```

### Generate Report

Generate detailed report:
```bash
python generate_report.py --format markdown
python generate_report.py --format json
python generate_report.py --format html
```

### Verbose Output

Run with detailed logging:
```bash
python check_compliance.py --verbose
```

### Custom Configuration

Use custom config file:
```bash
python check_compliance.py --config my_config.yaml
```

## Output

The checker generates:

1. **Console Output**: Real-time progress and summary
2. **Markdown Report**: `reports/compliance_report_YYYY-MM-DD.md`
3. **JSON Report**: `reports/compliance_report_YYYY-MM-DD.json`
4. **HTML Report**: `reports/compliance_report_YYYY-MM-DD.html`
5. **Logs**: `logs/compliance.log`

## Exit Codes

- `0`: All checks passed (compliance ≥ threshold)
- `1`: Some checks failed (compliance < threshold)
- `2`: Critical endpoints unavailable
- `3`: Server unreachable
- `4`: Configuration error

## Examples

### Example 1: Daily CI Check

```bash
#!/bin/bash
# daily_check.sh

python check_compliance.py \
  --config production.yaml \
  --format json \
  --output reports/daily_$(date +%Y%m%d).json

if [ $? -eq 0 ]; then
  echo "✅ Compliance check passed"
else
  echo "❌ Compliance check failed"
  # Send alert
  curl -X POST https://alerts.example.com/webhook \
    -d '{"status": "failed", "report": "reports/daily_'$(date +%Y%m%d)'.json"}'
fi
```

### Example 2: Pre-deployment Check

```bash
# Before deploying new vLLM version
python check_compliance.py \
  --config staging.yaml \
  --critical-only \
  --fail-fast

if [ $? -ne 0 ]; then
  echo "❌ Critical compliance issues found. Aborting deployment."
  exit 1
fi

echo "✅ Compliance verified. Proceeding with deployment."
```

### Example 3: Compare Two Servers

```bash
# Check production
python check_compliance.py --config prod.yaml --output reports/prod.json

# Check staging
python check_compliance.py --config staging.yaml --output reports/staging.json

# Compare
python utils/compare_reports.py reports/prod.json reports/staging.json
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Compliance Check

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight

jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          cd compliance_checker
          pip install -r requirements.txt

      - name: Run compliance check
        run: |
          cd compliance_checker
          python check_compliance.py

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: compliance-report
          path: compliance_checker/reports/
```

### GitLab CI

```yaml
compliance_check:
  stage: test
  script:
    - cd compliance_checker
    - pip install -r requirements.txt
    - python check_compliance.py
  artifacts:
    paths:
      - compliance_checker/reports/
    expire_in: 30 days
  only:
    - main
    - develop
```

## Troubleshooting

### Server Unreachable

```
Error: Cannot connect to http://192.168.228.43:8000
```

**Solutions:**
1. Check server is running: `curl http://192.168.228.43:8000/health`
2. Check firewall rules
3. Verify URL in `config.yaml`

### Authentication Errors

```
Error: 401 Unauthorized
```

**Solutions:**
1. Set API key: `export OPENAI_API_KEY=your_key`
2. Or enable in config:
   ```yaml
   auth:
     enabled: true
     api_key: "your_key"
   ```

### Streaming Timeout

```
Error: Streaming timeout after 60s
```

**Solutions:**
1. Increase timeout in config:
   ```yaml
   testing:
     streaming_timeout: 120
   ```
2. Use smaller test inputs
3. Check server performance

## Development

### Running Tests

```bash
pytest tests/
```

### Adding New Checks

1. Create checker class in `utils/validators.py`
2. Add test method in appropriate check file
3. Update `SPEC_TO_CODE_MAPPING.json`
4. Run tests

### Project Structure

```
compliance_checker/
├── config.yaml              # Configuration
├── requirements.txt         # Dependencies
├── README.md               # This file
├── check_compliance.py     # Main entry point
├── check_endpoints.py      # Endpoint tests
├── check_streaming.py      # Streaming tests
├── check_parameters.py     # Parameter tests
├── generate_report.py      # Report generator
├── utils/
│   ├── __init__.py
│   ├── api_client.py       # HTTP client wrapper
│   ├── spec_loader.py      # Load SPEC_TO_CODE_MAPPING.json
│   └── validators.py       # Validation utilities
├── reports/                # Generated reports
└── logs/                   # Log files
```

## Contributing

1. Follow PEP 8 style guide
2. Add tests for new features
3. Update documentation
4. Run compliance check before committing

## License

Same as vLLM project.

## Support

For issues or questions:
- GitHub Issues: https://github.com/vllm-project/vllm/issues
- Documentation: https://docs.vllm.ai/
