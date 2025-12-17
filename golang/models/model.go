package models

import (
	"time"

	"gorm.io/datatypes"
	"gorm.io/gorm"
)

// AccessRule mirrors the Python access_control shape
// 来源: backend/open_webui/models/models.py:84-100，定义读写用户/群组权限。
type AccessRule struct {
	GroupIDs []string `json:"group_ids" gorm:"serializer:json"`
	UserIDs  []string `json:"user_ids" gorm:"serializer:json"`
}

// AccessControl groups read/write rules.
// 来源: backend/open_webui/models/models.py:84-100，控制模型可见性与可写性。
type AccessControl struct {
	Read  *AccessRule `json:"read,omitempty" gorm:"serializer:json"`
	Write *AccessRule `json:"write,omitempty" gorm:"serializer:json"`
}

// Tag stores the user defined label for a model.
// 来源: backend/open_webui/routers/models.py:106-123，模型标签收集逻辑。
type Tag struct {
	Name string `json:"name"`
}

// ModelMeta collects the metadata keys observed in the Python implementation.
// profile_image_url/description/capabilities/tags 都在原始模型接口中被消费。
// 来源: backend/open_webui/models/models.py:39-52 与 routers/models.py:106-123。
type ModelMeta struct {
	ProfileImageURL string                 `json:"profile_image_url,omitempty"`
	Description     string                 `json:"description,omitempty"`
	Capabilities    map[string]any         `json:"capabilities,omitempty"`
	Tags            []Tag                  `json:"tags,omitempty"`
	Extra           map[string]interface{} `json:"extra,omitempty" gorm:"serializer:json"`
}

// ModelParams enumerates parameters used by OpenAI/Ollama payload helpers.
// 来源: backend/open_webui/utils/payload.py:31-127，包含 OpenAI 与 Ollama 支持的推理参数。
type ModelParams struct {
	Temperature      *float64           `json:"temperature,omitempty"`
	TopP             *float64           `json:"top_p,omitempty"`
	MinP             *float64           `json:"min_p,omitempty"`
	MaxTokens        *int               `json:"max_tokens,omitempty"`
	FrequencyPenalty *float64           `json:"frequency_penalty,omitempty"`
	PresencePenalty  *float64           `json:"presence_penalty,omitempty"`
	ReasoningEffort  string             `json:"reasoning_effort,omitempty"`
	Seed             any                `json:"seed,omitempty"`
	Stop             []string           `json:"stop,omitempty" gorm:"serializer:json"`
	LogitBias        map[string]float64 `json:"logit_bias,omitempty" gorm:"serializer:json"`
	ResponseFormat   map[string]any     `json:"response_format,omitempty" gorm:"serializer:json"`
	CustomParams     map[string]any     `json:"custom_params,omitempty" gorm:"serializer:json"`

	// Ollama root level options
	Format    any   `json:"format,omitempty"`
	KeepAlive any   `json:"keep_alive,omitempty"`
	Think     *bool `json:"think,omitempty"`

	// Ollama option map mirrors the apply_model_params_to_body_ollama mapping
	Mirostat      *int     `json:"mirostat,omitempty"`
	MirostatEta   *float64 `json:"mirostat_eta,omitempty"`
	MirostatTau   *float64 `json:"mirostat_tau,omitempty"`
	NumCtx        *int     `json:"num_ctx,omitempty"`
	NumBatch      *int     `json:"num_batch,omitempty"`
	NumKeep       *int     `json:"num_keep,omitempty"`
	NumPredict    *int     `json:"num_predict,omitempty"`
	RepeatLastN   *int     `json:"repeat_last_n,omitempty"`
	TopK          *int     `json:"top_k,omitempty"`
	RepeatPenalty *float64 `json:"repeat_penalty,omitempty"`
	NumGPU        *int     `json:"num_gpu,omitempty"`
	UseMMap       *bool    `json:"use_mmap,omitempty"`
	UseMLock      *bool    `json:"use_mlock,omitempty"`
	NumThread     *int     `json:"num_thread,omitempty"`
}

// Model represents the unified model table.
// 来源: backend/open_webui/models/models.py:55-105，字段与 Python 版保持一致。
type Model struct {
	ID           string         `json:"id" gorm:"primaryKey"`
	UserID       string         `json:"user_id"`
	BaseModelID  *string        `json:"base_model_id"`
	Name         string         `json:"name"`
	Params       ModelParams    `json:"params" gorm:"serializer:json"`
	Meta         ModelMeta      `json:"meta" gorm:"serializer:json"`
	Access       *AccessControl `json:"access_control,omitempty" gorm:"serializer:json"`
	IsActive     bool           `json:"is_active"`
	UpdatedAtSec int64          `json:"updated_at"`
	CreatedAtSec int64          `json:"created_at"`
}

// BeforeCreate stamps timestamps similar to the Python default.
// 参考: backend/open_webui/models/models.py:153-170，创建与更新时间戳。
func (m *Model) BeforeCreate(tx *gorm.DB) error {
	now := time.Now().Unix()
	if m.CreatedAtSec == 0 {
		m.CreatedAtSec = now
	}
	if m.UpdatedAtSec == 0 {
		m.UpdatedAtSec = now
	}
	return nil
}

// BeforeUpdate keeps updated_at in sync.
func (m *Model) BeforeUpdate(tx *gorm.DB) error {
	m.UpdatedAtSec = time.Now().Unix()
	return nil
}

// ModelListResponse mirrors the FastAPI response shape.
// 来源: backend/open_webui/models/models.py:138-141。
type ModelListResponse struct {
	Items []Model `json:"items"`
	Total int64   `json:"total"`
}

// ModelFilter carries query parameters from /list endpoint.
// 参考: backend/open_webui/routers/models.py:51-88。
type ModelFilter struct {
	Query      string
	ViewOption string
	Tag        string
	OrderBy    string
	Direction  string
	Page       int
	UserID     string
	GroupIDs   []string
}

// MergeMetaTags collects unique tags similar to routers/models.py:106-123。
func MergeMetaTags(models []Model) []string {
	seen := map[string]struct{}{}
	for _, m := range models {
		for _, tag := range m.Meta.Tags {
			if tag.Name == "" {
				continue
			}
			seen[tag.Name] = struct{}{}
		}
	}
	tags := make([]string, 0, len(seen))
	for name := range seen {
		tags = append(tags, name)
	}
	return tags
}

// ModelDTO is used for creation/update payloads.
// 与 Python ModelForm (backend/open_webui/models/models.py:143-150) 对应。
type ModelDTO struct {
	ID          string         `json:"id" binding:"required"`
	BaseModelID *string        `json:"base_model_id"`
	Name        string         `json:"name" binding:"required"`
	Meta        ModelMeta      `json:"meta"`
	Params      ModelParams    `json:"params"`
	Access      *AccessControl `json:"access_control"`
	IsActive    bool           `json:"is_active"`
	UserID      string         `json:"user_id"`
}

// ToModel converts DTO into persistence struct.
func (dto ModelDTO) ToModel() Model {
	return Model{
		ID:          dto.ID,
		UserID:      dto.UserID,
		BaseModelID: dto.BaseModelID,
		Name:        dto.Name,
		Params:      dto.Params,
		Meta:        dto.Meta,
		Access:      dto.Access,
		IsActive:    dto.IsActive,
	}
}

// ExternalModel describes models returned by providers.
// 对应 openai 模型聚合逻辑 backend/open_webui/routers/openai.py:520-538。
type ExternalModel struct {
	ID             string         `json:"id"`
	Name           string         `json:"name"`
	OwnedBy        string         `json:"owned_by"`
	ConnectionType string         `json:"connection_type"`
	URLs           []int          `json:"urls,omitempty"`
	URLIdx         *int           `json:"urlIdx,omitempty"`
	Raw            datatypes.JSON `json:"raw,omitempty"`
}
