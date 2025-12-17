package routers

import (
	"errors"
	"github.com/gin-gonic/gin"
)

// RegisterBackendRoutes 参考 backend/open_webui/routers 下各蓝图，按需挂载。
// 功能: 提供统一入口，后续可扩展用户、会话、文件等具体路由。
func RegisterBackendRoutes(r *gin.Engine) {
	// TODO: wire user/message/file routes translated from Python endpoints.
	r.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok"}) })
}

// ErrUnauthorized 对应 routers/common.py 权限检查的占位符。
var ErrUnauthorized = errors.New("unauthorized")
