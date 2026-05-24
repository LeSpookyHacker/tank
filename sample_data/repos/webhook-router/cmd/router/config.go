package main

import (
	"fmt"
	"os"
)

type config struct {
	Environment     string
	AWSRegion       string
	KinesisStream   string
	VaultAddr       string
	VaultRole       string
	EgressAllowlist []string
}

type WebhookConfig struct {
	CustomerID string
	URL        string
	EventKinds []string
	Active     bool
}

func loadConfig() (*config, error) {
	env := os.Getenv("ENV")
	if env == "" {
		env = "dev"
	}
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = "us-west-2"
	}
	vaultAddr := os.Getenv("VAULT_ADDR")
	if vaultAddr == "" {
		vaultAddr = "https://vault.helix.internal:8200"
	}
	stream := os.Getenv("KINESIS_STREAM")
	if stream == "" {
		stream = fmt.Sprintf("helix-%s-events", env)
	}
	return &config{
		Environment:   env,
		AWSRegion:     region,
		KinesisStream: stream,
		VaultAddr:     vaultAddr,
		VaultRole:     "webhook-router",
	}, nil
}
