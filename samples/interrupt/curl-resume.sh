thread_id="$1"
shift

checkpoint_id="$1"
shift

flavor="$1"
shift

if [ -z "$thread_id" ] || [ -z "$checkpoint_id" ] || [ -z "$flavor" ]; then
  echo "Usage: $0 <thread_id> <checkpoint_id> <flavor>"
  exit 1
fi

curl \
  -v \
  -X POST \
  "http://127.0.0.1:8000/thread/$thread_id/checkpoint/$checkpoint_id/resume" \
  -H "Content-Type: application/json" \
  -d '{"flavor":"'$flavor'"}'

echo
