package web

import (
	"database/sql"
	"encoding/json"
	"log"
	"time"

	"github.com/gofiber/fiber/v2"
)

// Config represents system configuration
type Config struct {
	MaxTokensPerTask        int     `json:"max_tokens_per_task"`
	MaxConcurrentTasks      int     `json:"max_concurrent_tasks"`
	HITLConfidenceThreshold int     `json:"hitl_confidence_threshold"`
	RateLimitRPM            int     `json:"rate_limit_rpm"`
	CircuitBreakerThreshold int     `json:"circuit_breaker_threshold"`
	CircuitResetTimeout     int     `json:"circuit_reset_timeout"`
	AzureDeployment         string  `json:"azure_deployment"`
	Temperature             float64 `json:"temperature"`
	RequestTimeout          int     `json:"request_timeout"`
	LogLevel                string  `json:"log_level"`
	EnableTracing           bool    `json:"enable_tracing"`
	EnableMetrics           bool    `json:"enable_metrics"`
	DebugMode               bool    `json:"debug_mode"`
	LastSaved               string  `json:"last_saved"`
}

// GetConfigPanel renders the config panel
func (h *Handler) GetConfigPanel(c *fiber.Ctx) error {
	config := h.getDefaultConfig()
	return Render(c, "config_panel", fiber.Map{
		"Config": config,
	})
}

// GetConfig returns current configuration as JSON
func (h *Handler) GetConfig(c *fiber.Ctx) error {
	config := h.getDefaultConfig()
	return c.JSON(fiber.Map{
		"Config": config,
	})
}

// getDefaultConfig returns default configuration, loading saved values from DB if available
func (h *Handler) getDefaultConfig() *Config {
	cfg := &Config{
		MaxTokensPerTask:        4000,
		MaxConcurrentTasks:      10,
		HITLConfidenceThreshold: 80,
		RateLimitRPM:            60,
		CircuitBreakerThreshold: 5,
		CircuitResetTimeout:     60,
		AzureDeployment:         "gpt-4",
		Temperature:             0.7,
		RequestTimeout:          30,
		LogLevel:                "info",
		EnableTracing:           true,
		EnableMetrics:           true,
		DebugMode:               false,
		LastSaved:               "",
	}

	if h.db != nil {
		var configJSON sql.NullString
		var updatedAt sql.NullTime
		err := h.db.QueryRow(`
			SELECT config_value::text, updated_at
			FROM app_config
			WHERE config_key = 'system_config'
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&configJSON, &updatedAt)
		if err == nil && configJSON.Valid && configJSON.String != "" {
			var saved Config
			if jsonErr := json.Unmarshal([]byte(configJSON.String), &saved); jsonErr == nil {
				if saved.MaxTokensPerTask > 0 {
					cfg.MaxTokensPerTask = saved.MaxTokensPerTask
				}
				if saved.MaxConcurrentTasks > 0 {
					cfg.MaxConcurrentTasks = saved.MaxConcurrentTasks
				}
				if saved.HITLConfidenceThreshold > 0 {
					cfg.HITLConfidenceThreshold = saved.HITLConfidenceThreshold
				}
				if saved.RateLimitRPM > 0 {
					cfg.RateLimitRPM = saved.RateLimitRPM
				}
				if saved.CircuitBreakerThreshold > 0 {
					cfg.CircuitBreakerThreshold = saved.CircuitBreakerThreshold
				}
				if saved.CircuitResetTimeout > 0 {
					cfg.CircuitResetTimeout = saved.CircuitResetTimeout
				}
				if saved.AzureDeployment != "" {
					cfg.AzureDeployment = saved.AzureDeployment
				}
				if saved.Temperature > 0 {
					cfg.Temperature = saved.Temperature
				}
				if saved.RequestTimeout > 0 {
					cfg.RequestTimeout = saved.RequestTimeout
				}
				if saved.LogLevel != "" {
					cfg.LogLevel = saved.LogLevel
				}
				cfg.EnableTracing = saved.EnableTracing
				cfg.EnableMetrics = saved.EnableMetrics
				cfg.DebugMode = saved.DebugMode
				if updatedAt.Valid {
					cfg.LastSaved = updatedAt.Time.Format(time.RFC3339)
				}
			}
		}
	}

	return cfg
}

// SaveConfig saves configuration changes
func (h *Handler) SaveConfig(c *fiber.Ctx) error {
	var req Config
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Invalid configuration data</div>`)
	}

	// Validate configuration
	if req.MaxTokensPerTask < 1000 || req.MaxTokensPerTask > 128000 {
		return c.Status(400).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Max tokens must be between 1000 and 128000</div>`)
	}

	if req.MaxConcurrentTasks < 1 || req.MaxConcurrentTasks > 100 {
		return c.Status(400).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Max concurrent tasks must be between 1 and 100</div>`)
	}

	// Persist configuration to app_config table
	if h.db != nil {
		configJSON, jsonErr := json.Marshal(req)
		if jsonErr == nil {
			_, execErr := h.db.Exec(`
				INSERT INTO app_config (config_key, config_value, updated_at)
				VALUES ('system_config', $1::jsonb, NOW())
				ON CONFLICT (config_key)
				DO UPDATE SET config_value = $1::jsonb, updated_at = NOW()
			`, string(configJSON))
			if execErr != nil {
				log.Printf("Failed to persist config: %v", execErr)
				return c.Status(500).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Failed to save configuration</div>`)
			}
		}
	}

	return c.SendString(`<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-center"><i class="fas fa-check-circle mr-2"></i>Configuration saved successfully!</div>`)
}

// ResetConfig resets configuration to defaults
func (h *Handler) ResetConfig(c *fiber.Ctx) error {
	if h.db != nil {
		_, err := h.db.Exec(`DELETE FROM app_config WHERE config_key = 'system_config'`)
		if err != nil {
			log.Printf("Failed to reset config: %v", err)
		}
	}
	return h.GetConfigPanel(c)
}
