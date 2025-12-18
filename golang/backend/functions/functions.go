package functions

import (
	"errors"
	"net/http"
)

// RequestContext 对标 backend/open_webui/functions.py 中的上下文对象，封装用户与会话数据。
type RequestContext struct {
	UserID    string
	SessionID string
	Metadata  map[string]any
}

// GenerateTitle 参考 functions.generate_title, 返回 TODO 响应。
// 功能: 根据会话生成标题。
func GenerateTitle(ctx RequestContext, messages []string) (string, error) {
	return "", errors.New("TODO: implement title generation with LLM provider")
}

// ProxyOpenAI 封装 openai 转发请求，当前仅留空位。
// TODO: 对接第三方 Python openai 库的等效实现。
func ProxyOpenAI(req *http.Request) (*http.Response, error) {
	return nil, errors.New("TODO: proxy OpenAI completion")
}

// ProxyOllama 对应 ollama 接口转发。
func ProxyOllama(req *http.Request) (*http.Response, error) {
	return nil, errors.New("TODO: proxy Ollama endpoint")
}
