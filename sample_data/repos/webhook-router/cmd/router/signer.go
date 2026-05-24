package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"time"

	vault "github.com/hashicorp/vault/api"
)

type HMACSigner struct {
	client *vault.Client
	env    string
}

func newHMACSigner(ctx context.Context, cfg *config) (*HMACSigner, error) {
	v, err := vault.NewClient(&vault.Config{Address: cfg.VaultAddr})
	if err != nil {
		return nil, fmt.Errorf("vault client: %w", err)
	}
	if err := authenticate(ctx, v, cfg.VaultRole); err != nil {
		return nil, err
	}
	return &HMACSigner{client: v, env: cfg.Environment}, nil
}

// Sign returns the value of the Helix-Signature header for the given
// customer + payload. The customer secret is fetched per-call (cached
// via Vault Agent in prod).
func (s *HMACSigner) Sign(customerID string, body []byte, ts time.Time) (string, error) {
	path := fmt.Sprintf("secret/data/webhook-router/%s/customer-secrets/%s", s.env, customerID)
	secret, err := s.client.Logical().Read(path)
	if err != nil {
		return "", fmt.Errorf("vault read %q: %w", path, err)
	}
	if secret == nil {
		return "", fmt.Errorf("no secret at %s", path)
	}
	data := secret.Data["data"].(map[string]any)
	key, _ := data["key"].(string)
	if key == "" {
		return "", fmt.Errorf("empty key at %s", path)
	}

	tsStr := fmt.Sprintf("%d", ts.Unix())
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write([]byte(tsStr))
	mac.Write([]byte("."))
	mac.Write(body)
	hex := hex.EncodeToString(mac.Sum(nil))
	return fmt.Sprintf("t=%s,v1=%s", tsStr, hex), nil
}

func authenticate(ctx context.Context, v *vault.Client, role string) error {
	// k8s auth flow elided for brevity
	_ = role
	return nil
}
