package tasks

import "errors"

// Scheduler 占位符，对标 backend/open_webui/tasks.py 内的 Celery/BackgroundScheduler。
type Scheduler struct{}

// Start 启动后台任务调度。
// TODO: 使用 Go 的 goroutine/cron 替换 Python APScheduler 实现。
func (s *Scheduler) Start() error {
	return errors.New("TODO: implement task scheduler")
}

// Stop 停止调度。
func (s *Scheduler) Stop() {}
