package models

import "time"

// User 对应 backend/open_webui/models/users.py 中的用户模型简化版。
type User struct {
	ID        string `gorm:"primaryKey"`
	Email     string `gorm:"uniqueIndex"`
	Username  string
	Password  string
	Role      string
	CreatedAt time.Time
}

// Conversation 对应 models/conversations.py，用于保存聊天记录元数据。
type Conversation struct {
	ID        string `gorm:"primaryKey"`
	Title     string
	UserID    string
	UpdatedAt time.Time
}

// Attachment 对应 models/files.py，记录文件元数据。
type Attachment struct {
	ID        string `gorm:"primaryKey"`
	Name      string
	Size      int64
	Type      string
	CreatedAt time.Time
}

// TODO: 补充其余模型字段，例如 Message, APIKey, ProviderProfile 等，按需从 Python 模块迁移。
