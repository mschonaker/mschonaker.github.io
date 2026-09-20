.PHONY: serve restart

serve:
	nohup python3 -m http.server 8080 --bind 0.0.0.0 > server.log 2>&1 &

restart:
	pkill -f "http.server 8080" 2>/dev/null; sleep 1; make serve