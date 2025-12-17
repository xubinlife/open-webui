package config

import (
	"errors"
	"log"
	"os"
	"path/filepath"
	"time"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

// Config 参考 backend/open_webui/config.py:43-66，持久化前端配置。
// 功能: 将UI配置保存在数据库中，版本字段用于迁移控制。
type Config struct {
	ID        uint           `gorm:"primaryKey"`
	Data      map[string]any `gorm:"type:json"`
	Version   int
	CreatedAt time.Time
	UpdatedAt *time.Time
}

// MigrationRunner 对应 config.run_migrations，占位符用于整合 Alembic 逻辑。
// TODO: 用 go-migrate 或 goose 实现数据库迁移，当前仅保留接口。
func MigrationRunner(db *gorm.DB, openWebUIDir string) error {
	log.Printf("[config] TODO run migrations under %s/migrations", openWebUIDir)
	return nil
}

// OpenDB 用于替代 Python get_db，默认采用 SQLite 便于本地演示。
func OpenDB(path string) (*gorm.DB, error) {
	if path == "" {
		return nil, errors.New("database path required")
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	db, err := gorm.Open(sqlite.Open(path), &gorm.Config{})
	if err != nil {
		return nil, err
	}
	if err := db.AutoMigrate(&Config{}); err != nil {
		return nil, err
	}
	return db, nil
}

// LoadConfig 映射 get_config，读取最新配置或使用默认值。
func LoadConfig(db *gorm.DB) map[string]any {
	var cfg Config
	if err := db.Order("id desc").First(&cfg).Error; err != nil {
		log.Printf("[config] fallback to default config: %v", err)
		return map[string]any{"version": 0, "ui": map[string]any{}}
	}
	return cfg.Data
}

// SaveConfig 替代 save_config，更新数据库并返回持久化结果。
func SaveConfig(db *gorm.DB, payload map[string]any) error {
	now := time.Now()
	var cfg Config
	if err := db.Order("id desc").First(&cfg).Error; err != nil {
		cfg = Config{Data: payload, Version: 0, CreatedAt: now}
		return db.Create(&cfg).Error
	}
	cfg.Data = payload
	cfg.UpdatedAt = &now
	return db.Save(&cfg).Error
}
