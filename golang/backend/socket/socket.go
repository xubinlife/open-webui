package socket

import "errors"

// Hub 对标 backend/open_webui/socket/__init__.py 的 websocket 事件中心。
type Hub struct{}

// Broadcast 推送消息到客户端。
func (h *Hub) Broadcast(channel string, payload any) error {
	return errors.New("TODO: implement websocket broadcast")
}
