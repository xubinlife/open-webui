package handlers

import (
	"net/http"
	"sort"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"open-webui/golang/models"
)

// RegisterModelRoutes wires model CRUD endpoints.
// 参考: backend/open_webui/routers/models.py:51-180, 198-228 等接口。
func RegisterModelRoutes(rg *gin.RouterGroup, db *gorm.DB) {
	rg.GET("/models/list", func(c *gin.Context) { listModels(c, db) })
	rg.GET("/models/base", func(c *gin.Context) { listBaseModels(c, db) })
	rg.GET("/models/tags", func(c *gin.Context) { listModelTags(c, db) })

	rg.POST("/models/create", func(c *gin.Context) { createModel(c, db) })
	rg.GET("/models/export", func(c *gin.Context) { exportModels(c, db) })
	rg.POST("/models/import", func(c *gin.Context) { importModels(c, db) })
	rg.POST("/models/sync", func(c *gin.Context) { syncModels(c, db) })

	rg.GET("/models/model", func(c *gin.Context) { getModel(c, db) })
	rg.POST("/models/model/toggle", func(c *gin.Context) { toggleModel(c, db) })
	rg.POST("/models/model/update", func(c *gin.Context) { updateModel(c, db) })
	rg.POST("/models/model/delete", func(c *gin.Context) { deleteModel(c, db) })
	rg.DELETE("/models/delete/all", func(c *gin.Context) { deleteAllModels(c, db) })
}

// RequestUser is a lightweight replacement for get_verified_user/get_admin_user.
// 使用 Header(X-User-Id/X-User-Role) 注入身份，默认 admin 便于演示。
type RequestUser struct {
	ID     string
	Role   string
	Groups []string
}

func userFromContext(c *gin.Context) RequestUser {
	id := c.GetHeader("X-User-Id")
	if id == "" {
		id = "admin"
	}
	role := c.GetHeader("X-User-Role")
	if role == "" {
		role = "admin"
	}
	groups := c.Request.Header.Values("X-User-Group")
	return RequestUser{ID: id, Role: role, Groups: groups}
}

func listModels(c *gin.Context, db *gorm.DB) {
	// Mirrors routers/models.py:get_models 查询与分页。
	user := userFromContext(c)
	page := 1
	if p := c.Query("page"); p != "" {
		if v, err := strconv.Atoi(p); err == nil && v > 0 {
			page = v
		}
	}
	filter := models.ModelFilter{
		Query:      c.Query("query"),
		ViewOption: c.Query("view_option"),
		Tag:        c.Query("tag"),
		OrderBy:    c.Query("order_by"),
		Direction:  c.Query("direction"),
		Page:       page,
		UserID:     user.ID,
		GroupIDs:   user.Groups,
	}

	var all []models.Model
	if err := db.Find(&all).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Filter only user defined (base_model_id not null)
	filtered := make([]models.Model, 0)
	for _, m := range all {
		if m.BaseModelID == nil {
			continue
		}
		if filter.Query != "" {
			if !strings.Contains(strings.ToLower(m.Name), strings.ToLower(filter.Query)) && !strings.Contains(strings.ToLower(m.ID), strings.ToLower(filter.Query)) {
				continue
			}
		}
		if filter.ViewOption == "created" && m.UserID != filter.UserID {
			continue
		}
		if filter.ViewOption == "shared" && m.UserID == filter.UserID {
			continue
		}
		if filter.Tag != "" {
			found := false
			for _, t := range m.Meta.Tags {
				if strings.EqualFold(t.Name, filter.Tag) {
					found = true
					break
				}
			}
			if !found {
				continue
			}
		}
		if user.Role != "admin" {
			if m.UserID == user.ID {
				filtered = append(filtered, m)
				continue
			}
			if !hasAccess(user, m.Access, "write") {
				continue
			}
		}
		filtered = append(filtered, m)
	}

	sort.Slice(filtered, func(i, j int) bool {
		switch filter.OrderBy {
		case "name":
			if filter.Direction == "asc" {
				return filtered[i].Name < filtered[j].Name
			}
			return filtered[i].Name > filtered[j].Name
		case "updated_at":
			if filter.Direction == "asc" {
				return filtered[i].UpdatedAtSec < filtered[j].UpdatedAtSec
			}
			return filtered[i].UpdatedAtSec > filtered[j].UpdatedAtSec
		default:
			if filter.Direction == "asc" {
				return filtered[i].CreatedAtSec < filtered[j].CreatedAtSec
			}
			return filtered[i].CreatedAtSec > filtered[j].CreatedAtSec
		}
	})

	const limit = 30
	start := (filter.Page - 1) * limit
	end := start + limit
	if start > len(filtered) {
		start = len(filtered)
	}
	if end > len(filtered) {
		end = len(filtered)
	}

	c.JSON(http.StatusOK, models.ModelListResponse{
		Items: filtered[start:end],
		Total: int64(len(filtered)),
	})
}

func listBaseModels(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:96-99
	var base []models.Model
	if err := db.Where("base_model_id IS NULL").Find(&base).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, base)
}

func listModelTags(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:106-123
	var all []models.Model
	if err := db.Find(&all).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	tags := models.MergeMetaTags(all)
	sort.Strings(tags)
	c.JSON(http.StatusOK, tags)
}

func createModel(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:130-166
	user := userFromContext(c)
	var dto models.ModelDTO
	if err := c.ShouldBindJSON(&dto); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if dto.UserID == "" {
		dto.UserID = user.ID
	}
	var existing models.Model
	if err := db.First(&existing, "id = ?", dto.ID).Error; err == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "model id taken"})
		return
	}
	model := dto.ToModel()
	if err := db.Create(&model).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, model)
}

func exportModels(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:173-187
	user := userFromContext(c)
	var modelsOut []models.Model
	if user.Role == "admin" {
		if err := db.Find(&modelsOut).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	} else {
		if err := db.Where("user_id = ?", user.ID).Find(&modelsOut).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}
	c.JSON(http.StatusOK, modelsOut)
}

func importModels(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:194-238
	user := userFromContext(c)
	var payload struct {
		Models []models.ModelDTO `json:"models"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	for _, dto := range payload.Models {
		if dto.ID == "" {
			continue
		}
		if dto.UserID == "" {
			dto.UserID = user.ID
		}
		var existing models.Model
		if err := db.First(&existing, "id = ?", dto.ID).Error; err == nil {
			db.Model(&existing).Updates(dto.ToModel())
		} else {
			db.Create(dto.ToModel())
		}
	}
	c.JSON(http.StatusOK, true)
}

func syncModels(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:243-289
	user := userFromContext(c)
	var payload struct {
		Models []models.Model `json:"models"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	newIDs := map[string]struct{}{}
	for i := range payload.Models {
		payload.Models[i].UserID = user.ID
		newIDs[payload.Models[i].ID] = struct{}{}
		db.Clauses(clause.OnConflict{
			Columns:   []clause.Column{{Name: "id"}},
			DoUpdates: clause.AssignmentColumns([]string{"user_id", "base_model_id", "name", "params", "meta", "access", "is_active", "updated_at_sec"}),
		}).Create(&payload.Models[i])
	}
	// delete removed
	if len(newIDs) == 0 {
		db.Session(&gorm.Session{AllowGlobalUpdate: true}).Delete(&models.Model{})
	} else {
		db.Where("id NOT IN ?", keys(newIDs)).Delete(&models.Model{})
	}
	c.JSON(http.StatusOK, payload.Models)
}

func getModel(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:301-340
	id := c.Query("id")
	user := userFromContext(c)
	var model models.Model
	if err := db.First(&model, "id = ?", id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
		return
	}
	if user.Role != "admin" && model.UserID != user.ID && !hasAccess(user, model.Access, "read") {
		c.JSON(http.StatusForbidden, gin.H{"error": "access denied"})
		return
	}
	c.JSON(http.StatusOK, model)
}

func toggleModel(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:342-377
	id := c.Query("id")
	user := userFromContext(c)
	var model models.Model
	if err := db.First(&model, "id = ?", id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
		return
	}
	if user.Role != "admin" && model.UserID != user.ID && !hasAccess(user, model.Access, "write") {
		c.JSON(http.StatusForbidden, gin.H{"error": "access denied"})
		return
	}
	model.IsActive = !model.IsActive
	if err := db.Save(&model).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, model)
}

func updateModel(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:379-397
	user := userFromContext(c)
	var dto models.ModelDTO
	if err := c.ShouldBindJSON(&dto); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	var model models.Model
	if err := db.First(&model, "id = ?", dto.ID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
		return
	}
	if user.Role != "admin" && model.UserID != user.ID && !hasAccess(user, model.Access, "write") {
		c.JSON(http.StatusForbidden, gin.H{"error": "access denied"})
		return
	}
	updates := dto.ToModel()
	updates.CreatedAtSec = model.CreatedAtSec
	if err := db.Model(&model).Updates(updates).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, model)
}

func deleteModel(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:399-430
	user := userFromContext(c)
	var payload struct {
		ID string `json:"id"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	var model models.Model
	if err := db.First(&model, "id = ?", payload.ID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
		return
	}
	if user.Role != "admin" && model.UserID != user.ID && !hasAccess(user, model.Access, "write") {
		c.JSON(http.StatusForbidden, gin.H{"error": "access denied"})
		return
	}
	if err := db.Delete(&model).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, true)
}

func deleteAllModels(c *gin.Context, db *gorm.DB) {
	// backend/open_webui/routers/models.py:432-437
	if err := db.Session(&gorm.Session{AllowGlobalUpdate: true}).Delete(&models.Model{}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, true)
}

func hasAccess(user RequestUser, ac *models.AccessControl, perm string) bool {
	if ac == nil {
		return true
	}
	var rule *models.AccessRule
	if perm == "write" {
		rule = ac.Write
	} else {
		rule = ac.Read
	}
	if rule == nil {
		return false
	}
	for _, id := range rule.UserIDs {
		if id == user.ID {
			return true
		}
	}
	for _, gid := range rule.GroupIDs {
		for _, ug := range user.Groups {
			if gid == ug {
				return true
			}
		}
	}
	return false
}

func keys(m map[string]struct{}) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}
