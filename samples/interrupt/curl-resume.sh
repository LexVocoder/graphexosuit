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
  --verbose \
  --request POST \
  "http://127.0.0.1:8000/thread/$thread_id/checkpoint/$checkpoint_id/resume" \
  --header "Content-Type: application/json" \
  --data '{"flavor":"'$flavor'"}'

echo
