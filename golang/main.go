package main

import (
	"log"

	"github.com/gin-gonic/gin"

	"open-webui/golang/database"
	"open-webui/golang/handlers"
	"open-webui/golang/models"
)

// main 启动 gin 路由，挂载模型管理与外部链接管理接口。
func main() {
	db := database.Init("")
	database.MustMigrate(db, &models.Model{}, &models.ExternalLink{})

	r := gin.Default()
	api := r.Group("/api")
	handlers.RegisterExternalRoutes(api, db)
	handlers.RegisterModelRoutes(api, db)

	log.Println("Go reimplementation of Open WebUI model services listening on :8080")
	if err := r.Run(":8080"); err != nil {
		log.Fatalf("failed to start server: %v", err)
	}
}
