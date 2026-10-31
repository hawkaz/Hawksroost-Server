# Hawksroost Server — convenience targets. Run on the cabin host.
.PHONY: preflight up down logs verify ps

preflight:   ## Check dongle, blacklist, and SDR contention before starting
	./scripts/preflight.sh

up:          ## Start the recorder (Step 1)
	docker compose up -d rtlsdr-airband

down:        ## Stop the stack
	docker compose down

logs:        ## Follow recorder logs
	docker compose logs -f rtlsdr-airband

verify:      ## List the most recent recordings
	./scripts/verify-recording.sh

ps:          ## Show compose service status
	docker compose ps
