package database

import (
	"fmt"
	"log"
	"path/filepath"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

// Init opens a sqlite database for demo purposes.
// 数据库初始化，便于在 Go 版本中持久化模型与外部链接记录。
func Init(dbPath string) *gorm.DB {
	if dbPath == "" {
		dbPath = filepath.Join("data", "openwebui.db")
	}

	db, err := gorm.Open(sqlite.Open(dbPath), &gorm.Config{})
	if err != nil {
		log.Fatalf("failed to open database %s: %v", dbPath, err)
	}
	return db
}

// MustMigrate runs AutoMigrate on the provided models.
// 自动迁移用于创建结构化表。
func MustMigrate(db *gorm.DB, models ...interface{}) {
	if err := db.AutoMigrate(models...); err != nil {
		panic(fmt.Errorf("auto migrate failed: %w", err))
	}
}
