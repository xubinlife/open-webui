package storage

import "errors"

// FileStore 参考 backend/open_webui/storage/__init__.py，封装文件读写。
type FileStore struct {
	BasePath string
}

// Save 存储文件。
func (s *FileStore) Save(name string, content []byte) error {
	return errors.New("TODO: implement file save")
}

// Load 读取文件内容。
func (s *FileStore) Load(name string) ([]byte, error) {
	return nil, errors.New("TODO: implement file load")
}
