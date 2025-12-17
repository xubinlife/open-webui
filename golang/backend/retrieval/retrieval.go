package retrieval

import "errors"

// Pipeline 映射 backend/open_webui/retrieval/base.py 的检索管道。
type Pipeline struct{}

// Query 执行向量检索。
func (p *Pipeline) Query(text string, topK int) ([]string, error) {
	return nil, errors.New("TODO: implement retrieval pipeline")
}
