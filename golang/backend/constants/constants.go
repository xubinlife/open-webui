package constants

// 参考 backend/open_webui/constants.py:1-120，摘取通用提示文案。
// 功能: 将常用消息枚举化，便于后续 API 返回复用。
const (
	MessageModelAdded   = "The model '%s' has been added successfully."
	MessageModelDeleted = "The model '%s' has been deleted successfully."

	ErrEnvVarNotFound   = "Required environment variable not found. Terminating now."
	ErrUnauthorized     = "401 Unauthorized"
	ErrAccessProhibited = "You do not have permission to access this resource. Please contact your administrator for assistance."
	ErrNotFound         = "We could not find what you're looking for :/"
	ErrModelNotFound    = "Model '%s' was not found"
	ErrOllamaNotFound   = "WebUI could not connect to Ollama"
	ErrEmptyContent     = "The content provided is empty. Please ensure that there is text or data present before proceeding."
)

// Task names mirror TASKS 枚举，供任务调度使用。
const (
	TaskTitleGeneration        = "title_generation"
	TaskFollowUpGeneration     = "follow_up_generation"
	TaskTagsGeneration         = "tags_generation"
	TaskEmojiGeneration        = "emoji_generation"
	TaskQueryGeneration        = "query_generation"
	TaskImagePromptGeneration  = "image_prompt_generation"
	TaskAutocompleteGeneration = "autocomplete_generation"
	TaskFunctionCalling        = "function_calling"
	TaskMoaResponseGeneration  = "moa_response_generation"
)
