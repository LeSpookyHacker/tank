// webhook-router entrypoint.
//
// Consumes the helix-prod-events Kinesis stream and fans out HMAC-signed
// HTTPS POSTs to customer-supplied webhook URLs. Retries with
// exponential backoff up to 24 hours.
package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	zerolog.SetGlobalLevel(zerolog.InfoLevel)
	log.Info().Str("svc", "webhook-router").Msg("starting up")

	cfg, err := loadConfig()
	if err != nil {
		log.Fatal().Err(err).Msg("load config")
	}

	store, err := newDynamoStore(context.Background(), cfg)
	if err != nil {
		log.Fatal().Err(err).Msg("dynamo init")
	}

	signer, err := newHMACSigner(context.Background(), cfg)
	if err != nil {
		log.Fatal().Err(err).Msg("vault signer init")
	}

	// metrics
	go func() {
		mux := http.NewServeMux()
		mux.Handle("/metrics", promhttp.Handler())
		_ = http.ListenAndServe(":9090", mux)
	}()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	consumer := newKinesisConsumer(cfg, store, signer)
	go consumer.Run(ctx)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	log.Info().Msg("shutting down (24h drain window)")
	shutdownCtx, sCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer sCancel()
	consumer.Drain(shutdownCtx)
}
