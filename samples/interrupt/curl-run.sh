curl \
  -v \
  'http://127.0.0.1:8000/run' \
  -H 'Content-Type: application/json' \
  -d '{"input":{"value": 42}}'

echo
