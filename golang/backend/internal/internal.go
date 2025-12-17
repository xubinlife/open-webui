package internal

import "errors"

// AuthValidator 对应 backend/open_webui/internal/auth.py，负责校验用户权限。
type AuthValidator struct{}

// VerifyToken 校验 JWT/Session 信息。
func (a *AuthValidator) VerifyToken(token string) (string, error) {
	return "", errors.New("TODO: implement auth verification")
}

// DBMigration 占位，映射 internal/db.py 的数据库初始化逻辑。
func DBMigration() error {
	return errors.New("TODO: port SQLAlchemy migrations to GORM")
}
