package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/datatypes"
	"gorm.io/gorm"

	"open-webui/golang/models"
)

// RegisterExternalRoutes sets unified routes for OpenAI/Ollama links.
// 参考: backend/open_webui/routers/openai.py:209-267 与 backend/open_webui/routers/ollama.py:269-305 的配置接口。
func RegisterExternalRoutes(rg *gin.RouterGroup, db *gorm.DB) {
	rg.GET("/external-links", func(c *gin.Context) { listExternalLinks(c, db) })
	rg.POST("/external-links", func(c *gin.Context) { createExternalLink(c, db) })
	rg.PUT("/external-links/:id", func(c *gin.Context) { updateExternalLink(c, db) })
	rg.POST("/external-links/:id/verify", func(c *gin.Context) { verifyExternalLink(c, db) })
	rg.GET("/external-links/:id/models", func(c *gin.Context) { fetchExternalModels(c, db) })
	rg.GET("/external-links/models", func(c *gin.Context) { aggregateExternalModels(c, db) })
}

func listExternalLinks(c *gin.Context, db *gorm.DB) {
	var links []models.ExternalLink
	if err := db.Find(&links).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, links)
}

func createExternalLink(c *gin.Context, db *gorm.DB) {
	var dto models.ExternalLink
	if err := c.ShouldBindJSON(&dto); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if dto.Type == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "type is required (openai|ollama)"})
		return
	}
	if err := db.Create(&dto).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, dto)
}

func updateExternalLink(c *gin.Context, db *gorm.DB) {
	var link models.ExternalLink
	if err := db.First(&link, c.Param("id")).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "link not found"})
		return
	}
	var dto models.ExternalLink
	if err := c.ShouldBindJSON(&dto); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	dto.ID = link.ID
	if err := db.Model(&link).Updates(dto).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, dto)
}

// verifyExternalLink reuses provider-specific verification steps.
// OpenAI: backend/open_webui/routers/openai.py:637-709
// Ollama: backend/open_webui/routers/ollama.py:219-266
func verifyExternalLink(c *gin.Context, db *gorm.DB) {
	var link models.ExternalLink
	if err := db.First(&link, c.Param("id")).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "link not found"})
		return
	}

	client := &http.Client{Timeout: 10 * time.Second}
	switch strings.ToLower(link.Type) {
	case "openai":
		url := strings.TrimSuffix(link.BaseURL, "/")
		req, _ := http.NewRequestWithContext(c.Request.Context(), http.MethodGet, url+"/models", nil)
		if link.Azure {
			apiVersion := link.APIVersion
			if apiVersion == "" {
				apiVersion = "2023-03-15-preview"
			}
			req, _ = http.NewRequestWithContext(c.Request.Context(), http.MethodGet, url+"/openai/models?api-version="+apiVersion, nil)
		}
		if link.AuthType != "none" && link.APIKey != "" {
			req.Header.Set("Authorization", "Bearer "+link.APIKey)
		}
		resp, err := client.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
			return
		}
		defer resp.Body.Close()
		c.JSON(resp.StatusCode, gin.H{"status": resp.Status})
	case "ollama":
		url := strings.TrimSuffix(link.BaseURL, "/")
		req, _ := http.NewRequestWithContext(c.Request.Context(), http.MethodGet, url+"/api/version", nil)
		if link.APIKey != "" {
			req.Header.Set("Authorization", "Bearer "+link.APIKey)
		}
		resp, err := client.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
			return
		}
		defer resp.Body.Close()
		c.JSON(resp.StatusCode, gin.H{"status": resp.Status})
	default:
		c.JSON(http.StatusBadRequest, gin.H{"error": "unsupported type"})
	}
}

// fetchExternalModels requests models from a single link.
// OpenAI 聚合逻辑参考 backend/open_webui/routers/openai.py:345-538；
// Ollama 模型列表参考 backend/open_webui/routers/ollama.py:325-360。
func fetchExternalModels(c *gin.Context, db *gorm.DB) {
	var link models.ExternalLink
	if err := db.First(&link, c.Param("id")).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "link not found"})
		return
	}

	modelsList, status, err := pullModelsFromLink(c.Request.Context(), link, nil)
	if err != nil {
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, modelsList)
}

// aggregateExternalModels merges every link into a deduped list with url indexes.
// 逻辑来源 openai get_all_models 与 ollama merge_ollama_models_lists。
func aggregateExternalModels(c *gin.Context, db *gorm.DB) {
	var links []models.ExternalLink
	if err := db.Find(&links).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	merged := map[string]models.ExternalModel{}
	for idx, link := range links {
		list, status, err := pullModelsFromLink(c.Request.Context(), link, &idx)
		if err != nil {
			c.JSON(status, gin.H{"error": err.Error()})
			return
		}
		for _, m := range list {
			if existing, ok := merged[m.ID]; ok {
				if len(existing.URLs) == 0 && existing.URLIdx != nil {
					existing.URLs = append(existing.URLs, *existing.URLIdx)
					existing.URLIdx = nil
				}
				if m.URLIdx != nil {
					existing.URLs = append(existing.URLs, *m.URLIdx)
				}
				merged[m.ID] = existing
			} else {
				merged[m.ID] = m
			}
		}
	}

	out := make([]models.ExternalModel, 0, len(merged))
	for _, m := range merged {
		out = append(out, m)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	c.JSON(http.StatusOK, gin.H{"data": out})
}

func pullModelsFromLink(ctx context.Context, link models.ExternalLink, idx *int) ([]models.ExternalModel, int, error) {
	client := &http.Client{Timeout: 15 * time.Second}
	base := strings.TrimSuffix(link.BaseURL, "/")

	switch strings.ToLower(link.Type) {
	case "openai":
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, base+"/models", nil)
		if link.Azure {
			apiVersion := link.APIVersion
			if apiVersion == "" {
				apiVersion = "2023-03-15-preview"
			}
			req, _ = http.NewRequestWithContext(ctx, http.MethodGet, base+"/openai/models?api-version="+apiVersion, nil)
		}
		if link.AuthType != "none" && link.APIKey != "" {
			req.Header.Set("Authorization", "Bearer "+link.APIKey)
		}
		resp, err := client.Do(req)
		if err != nil {
			return nil, http.StatusBadGateway, err
		}
		defer resp.Body.Close()

		if resp.StatusCode >= 400 {
			return nil, resp.StatusCode, fmt.Errorf("remote returned %s", resp.Status)
		}

		var payload struct {
			Data []map[string]any `json:"data"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
			return nil, http.StatusBadGateway, err
		}
		if len(payload.Data) == 0 && len(link.ModelIDs) > 0 {
			for _, id := range link.ModelIDs {
				payload.Data = append(payload.Data, map[string]any{"id": id, "name": id})
			}
		}
		var out []models.ExternalModel
		for _, item := range payload.Data {
			id := fmt.Sprint(item["id"])
			if strings.Contains(base, "api.openai.com") {
				skip := []string{"babbage", "dall-e", "davinci", "embedding", "tts", "whisper"}
				bad := false
				for _, s := range skip {
					if strings.Contains(id, s) {
						bad = true
						break
					}
				}
				if bad {
					continue
				}
			}
			em := models.ExternalModel{
				ID:             id,
				Name:           fmt.Sprint(item["name"]),
				OwnedBy:        "openai",
				ConnectionType: link.ConnectionType,
				URLIdx:         idx,
			}
			if raw, err := json.Marshal(item); err == nil {
				em.Raw = datatypes.JSON(raw)
			}
			if link.PrefixID != "" {
				em.ID = link.PrefixID + "." + em.ID
			}
			if len(link.Tags) > 0 {
				if em.Raw == nil {
					em.Raw = datatypes.JSON([]byte("{}"))
				}
			}
			out = append(out, em)
		}
		return out, http.StatusOK, nil

	case "ollama":
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, base+"/api/tags", nil)
		if link.APIKey != "" {
			req.Header.Set("Authorization", "Bearer "+link.APIKey)
		}
		resp, err := client.Do(req)
		if err != nil {
			return nil, http.StatusBadGateway, err
		}
		defer resp.Body.Close()
		if resp.StatusCode >= 400 {
			return nil, resp.StatusCode, fmt.Errorf("remote returned %s", resp.Status)
		}
		var payload struct {
			Models []map[string]any `json:"models"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
			return nil, http.StatusBadGateway, err
		}
		if len(link.ModelIDs) > 0 {
			filtered := payload.Models[:0]
			for _, m := range payload.Models {
				id := fmt.Sprint(m["model"])
				for _, allowed := range link.ModelIDs {
					if id == allowed {
						filtered = append(filtered, m)
						break
					}
				}
			}
			payload.Models = filtered
		}
		var out []models.ExternalModel
		for _, m := range payload.Models {
			id := fmt.Sprint(m["model"])
			if link.PrefixID != "" {
				id = link.PrefixID + "." + id
			}
			em := models.ExternalModel{
				ID:             id,
				Name:           id,
				OwnedBy:        "ollama",
				ConnectionType: link.ConnectionType,
				URLIdx:         idx,
			}
			if link.ConnectionType == "" {
				em.ConnectionType = "local"
			}
			if raw, err := json.Marshal(m); err == nil {
				em.Raw = datatypes.JSON(raw)
			}
			out = append(out, em)
		}
		return out, http.StatusOK, nil
	default:
		return nil, http.StatusBadRequest, fmt.Errorf("unknown provider type")
	}
}
