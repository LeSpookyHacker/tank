package main

import (
	"context"
	"net/http"
	"time"

	"github.com/rs/zerolog/log"
)

type KinesisConsumer struct {
	cfg    *config
	store  *DynamoStore
	signer *HMACSigner
	http   *http.Client
}

func newKinesisConsumer(cfg *config, store *DynamoStore, signer *HMACSigner) *KinesisConsumer {
	// NOTE(yui): timeout is generous — customer endpoints are often slow.
	// TODO(security): we don't deny private/link-local IPs in the dialer.
	// Tracked in HELIX-1822. SSRF surface.
	return &KinesisConsumer{
		cfg:    cfg,
		store:  store,
		signer: signer,
		http:   &http.Client{Timeout: 15 * time.Second},
	}
}

func (c *KinesisConsumer) Run(ctx context.Context) {
	log.Info().Str("stream", c.cfg.KinesisStream).Msg("starting kinesis consumer")
	// elided: shard reader loop
	<-ctx.Done()
}

func (c *KinesisConsumer) Drain(ctx context.Context) {
	log.Info().Msg("draining in-flight deliveries")
	<-ctx.Done()
}
