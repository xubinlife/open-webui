package backend

import (
	"log"

	"github.com/gin-gonic/gin"

	backendConfig "open-webui/golang/backend/config"
	"open-webui/golang/backend/env"
	"open-webui/golang/backend/routers"
)

// Server 聚合 Gin、配置与数据库，作为 Python backend/main.py 的 Go 入口替代。
// 参考: backend/open_webui/main.py:33-120。
type Server struct {
	Engine *gin.Engine
}

// NewServer 初始化基础依赖。
func NewServer() (*Server, error) {
	e := env.Load()
	db, err := backendConfig.OpenDB(e.DatabaseURL)
	if err != nil {
		return nil, err
	}
	if err := backendConfig.MigrationRunner(db, e.OpenWebUIDir); err != nil {
		log.Printf("[backend] migration placeholder: %v", err)
	}

	router := gin.Default()
	routers.RegisterBackendRoutes(router)
	return &Server{Engine: router}, nil
}

// Run 启动 HTTP 服务。
func (s *Server) Run(addr string) error {
	return s.Engine.Run(addr)
}
