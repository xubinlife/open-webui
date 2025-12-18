package models

import "time"

// ExternalLink unifies OpenAI/Ollama connection definitions.
// 来源: backend/open_webui/routers/openai.py:209-267 与 backend/open_webui/routers/ollama.py:269-305。
type ExternalLink struct {
	ID uint `json:"id" gorm:"primaryKey"`

	Name string `json:"name"`
	Type string `json:"type"` // openai 或 ollama

	BaseURL string `json:"base_url"`
	APIKey  string `json:"api_key"`

	Enable         bool                   `json:"enable"`
	ConnectionType string                 `json:"connection_type"`
	PrefixID       string                 `json:"prefix_id"`
	Tags           []string               `json:"tags" gorm:"serializer:json"`
	ModelIDs       []string               `json:"model_ids" gorm:"serializer:json"`
	Headers        map[string]string      `json:"headers" gorm:"serializer:json"`
	AuthType       string                 `json:"auth_type"`
	APIVersion     string                 `json:"api_version"`
	Azure          bool                   `json:"azure"`
	Meta           map[string]interface{} `json:"meta" gorm:"serializer:json"`

	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// TableName keeps the table short and explicit.
func (ExternalLink) TableName() string { return "external_links" }
