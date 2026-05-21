package main

import (
	"context"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
)

type DynamoStore struct {
	client          *dynamodb.Client
	configsTable    string
	eventsTable     string
}

func newDynamoStore(ctx context.Context, cfg *config) (*DynamoStore, error) {
	awsCfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(cfg.AWSRegion))
	if err != nil {
		return nil, err
	}
	return &DynamoStore{
		client:       dynamodb.NewFromConfig(awsCfg),
		configsTable: "helix-webhook-configs",
		eventsTable:  "helix-webhook-events",
	}, nil
}

// LookupCustomer returns the customer-side webhook config for a given
// customer_id + event_kind. Returns nil if no subscription matches.
func (s *DynamoStore) LookupCustomer(ctx context.Context,
	customerID, eventKind string) (*WebhookConfig, error) {
	// elided
	_ = ctx
	_ = customerID
	_ = eventKind
	_ = aws.String
	return nil, nil
}
