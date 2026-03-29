package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	maxbot "github.com/max-messenger/max-bot-api-client-go"
	"github.com/max-messenger/max-bot-api-client-go/schemes"
)

// Settings хранит настройки запуска MAX-адаптера.
type Settings struct {
	MaxBotToken               string
	BotCoreURL                string
	BotCoreTimeoutSeconds     time.Duration
	InternalPort              string
	RequestDelayAfterFailures time.Duration
}

// IncomingMessage описывает JSON-контракт входящего сообщения для core.
type IncomingMessage struct {
	Platform    string         `json:"platform"`
	MessageType string         `json:"message_type"`
	UserID      string         `json:"user_id"`
	ChatID      string         `json:"chat_id"`
	Text        string         `json:"text"`
	MessageID   string         `json:"message_id,omitempty"`
	Timestamp   string         `json:"timestamp,omitempty"`
	Metadata    map[string]any `json:"metadata"`
}

// CallbackEvent описывает JSON-контракт callback-события для core.
type CallbackEvent struct {
	Platform     string         `json:"platform"`
	UserID       string         `json:"user_id"`
	ChatID       string         `json:"chat_id"`
	CallbackData string         `json:"callback_data"`
	MessageID    string         `json:"message_id,omitempty"`
	Metadata     map[string]any `json:"metadata"`
}

// OutgoingAction описывает действие, которое должен выполнить адаптер.
type OutgoingAction struct {
	Type     string           `json:"type"`
	Text     string           `json:"text,omitempty"`
	Buttons  [][]InlineButton `json:"buttons,omitempty"`
	Metadata map[string]any   `json:"metadata,omitempty"`
}

// BotResponse описывает ответ core-сервиса.
type BotResponse struct {
	Actions []OutgoingAction `json:"actions"`
}

// InlineButton описывает inline-кнопку из ответа core.
type InlineButton struct {
	Text         string `json:"text"`
	CallbackData string `json:"callback_data"`
}

// InternalSendRequest описывает внутренний запрос на отправку сообщения через MAX-адаптер.
type InternalSendRequest struct {
	UserID string `json:"user_id,omitempty"`
	ChatID string `json:"chat_id,omitempty"`
	Text   string `json:"text"`
}

// CoreClient отправляет нормализованные сообщения в общий core.
type CoreClient struct {
	baseURL string
	client  *http.Client
}

// NewSettings считывает настройки из переменных окружения.
func NewSettings() Settings {
	timeoutSeconds := 10 * time.Second
	if rawTimeout := os.Getenv("BOT_CORE_TIMEOUT_SECONDS"); rawTimeout != "" {
		if parsedTimeout, err := time.ParseDuration(rawTimeout + "s"); err == nil {
			timeoutSeconds = parsedTimeout
		}
	}

	return Settings{
		MaxBotToken:               os.Getenv("MAX_BOT_TOKEN"),
		BotCoreURL:                valueOrDefault(os.Getenv("BOT_CORE_URL"), "http://127.0.0.1:8000"),
		BotCoreTimeoutSeconds:     timeoutSeconds,
		InternalPort:              valueOrDefault(os.Getenv("MAX_BOT_INTERNAL_PORT"), "8081"),
		RequestDelayAfterFailures: 2 * time.Second,
	}
}

// NewCoreClient создает HTTP-клиент для вызовов core-сервиса.
func NewCoreClient(settings Settings) *CoreClient {
	return &CoreClient{
		baseURL: settings.BotCoreURL,
		client: &http.Client{
			Timeout: settings.BotCoreTimeoutSeconds,
		},
	}
}

// ProcessMessage отправляет сообщение в core и возвращает список действий.
func (c *CoreClient) ProcessMessage(ctx context.Context, payload IncomingMessage) (BotResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return BotResponse{}, fmt.Errorf("не удалось сериализовать запрос в core: %w", err)
	}

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+"/messages",
		bytes.NewReader(body),
	)
	if err != nil {
		return BotResponse{}, fmt.Errorf("не удалось создать запрос в core: %w", err)
	}

	request.Header.Set("Content-Type", "application/json")

	response, err := c.client.Do(request)
	if err != nil {
		return BotResponse{}, fmt.Errorf("не удалось отправить запрос в core: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode >= http.StatusBadRequest {
		responseBody, _ := io.ReadAll(response.Body)
		return BotResponse{}, fmt.Errorf(
			"core вернул статус %d: %s",
			response.StatusCode,
			string(responseBody),
		)
	}

	var botResponse BotResponse
	if err := json.NewDecoder(response.Body).Decode(&botResponse); err != nil {
		return BotResponse{}, fmt.Errorf("не удалось разобрать ответ core: %w", err)
	}

	return botResponse, nil
}

// ProcessCallback отправляет callback-событие в core и возвращает список действий.
func (c *CoreClient) ProcessCallback(ctx context.Context, payload CallbackEvent) (BotResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return BotResponse{}, fmt.Errorf("не удалось сериализовать callback в core: %w", err)
	}

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+"/callbacks",
		bytes.NewReader(body),
	)
	if err != nil {
		return BotResponse{}, fmt.Errorf("не удалось создать callback запрос в core: %w", err)
	}

	request.Header.Set("Content-Type", "application/json")

	response, err := c.client.Do(request)
	if err != nil {
		return BotResponse{}, fmt.Errorf("не удалось отправить callback в core: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode >= http.StatusBadRequest {
		responseBody, _ := io.ReadAll(response.Body)
		return BotResponse{}, fmt.Errorf(
			"core вернул статус %d для callback: %s",
			response.StatusCode,
			string(responseBody),
		)
	}

	var botResponse BotResponse
	if err := json.NewDecoder(response.Body).Decode(&botResponse); err != nil {
		return BotResponse{}, fmt.Errorf("не удалось разобрать callback ответ core: %w", err)
	}

	return botResponse, nil
}

func main() {
	settings := NewSettings()
	if settings.MaxBotToken == "" {
		log.Fatal("MAX_BOT_TOKEN is not set")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()

	api, err := maxbot.New(settings.MaxBotToken)
	if err != nil {
		log.Fatalf("не удалось создать MAX API клиент: %v", err)
	}

	coreClient := NewCoreClient(settings)

	server := startInternalServer(ctx, settings, api)
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Printf("ошибка остановки internal MAX server: %v", err)
		}
	}()

	for update := range api.GetUpdates(ctx) {
		if err := handleUpdate(ctx, api, coreClient, update); err != nil {
			log.Printf("ошибка обработки MAX update: %v", err)
			time.Sleep(settings.RequestDelayAfterFailures)
		}
	}
}

// handleUpdate обрабатывает только текстовые сообщения и пересылает их в core.
func handleUpdate(
	ctx context.Context,
	api *maxbot.Api,
	coreClient *CoreClient,
	update any,
) error {
	if callbackUpdate, ok := update.(*schemes.MessageCallbackUpdate); ok {
		return handleCallbackUpdate(ctx, api, coreClient, callbackUpdate)
	}

	messageUpdate, ok := update.(*schemes.MessageCreatedUpdate)
	if !ok {
		return nil
	}

	payload, err := buildIncomingMessage(messageUpdate)
	if err != nil {
		return err
	}

	response, err := coreClient.ProcessMessage(ctx, payload)
	if err != nil {
		if sendErr := sendFallbackMessage(ctx, api, messageUpdate); sendErr != nil {
			return errors.Join(err, sendErr)
		}
		return err
	}

	for _, action := range response.Actions {
		if action.Type != "send_text" || action.Text == "" {
			continue
		}

		var chatID int64
		var userID int64
		switch {
		case messageUpdate.Message.Recipient.ChatId != 0:
			chatID = messageUpdate.Message.Recipient.ChatId
		case messageUpdate.Message.Sender.UserId != 0:
			userID = messageUpdate.Message.Sender.UserId
		default:
			return fmt.Errorf("в MAX update нет chat_id и user_id для ответа")
		}

		if err := sendMessage(ctx, api, userID, chatID, action.Text, action.Buttons); err != nil {
			return fmt.Errorf("не удалось отправить ответ в MAX: %w", err)
		}
	}

	return nil
}

func handleCallbackUpdate(
	ctx context.Context,
	api *maxbot.Api,
	coreClient *CoreClient,
	update *schemes.MessageCallbackUpdate,
) error {
	callbackEvent, err := buildCallbackEvent(update)
	if err != nil {
		return err
	}

	response, err := coreClient.ProcessCallback(ctx, callbackEvent)
	if err != nil {
		return err
	}

	userID, err := parseOptionalInt64(callbackEvent.UserID)
	if err != nil {
		return err
	}
	chatID, err := parseOptionalInt64(callbackEvent.ChatID)
	if err != nil {
		return err
	}

	for _, action := range response.Actions {
		if action.Type != "send_text" || action.Text == "" {
			continue
		}

		if err := sendMessage(ctx, api, userID, chatID, action.Text, action.Buttons); err != nil {
			return fmt.Errorf("не удалось отправить callback ответ в MAX: %w", err)
		}
	}

	return nil
}

// buildIncomingMessage нормализует MAX update к контракту core.
func buildIncomingMessage(update *schemes.MessageCreatedUpdate) (IncomingMessage, error) {
	message := update.Message

	var userID string
	if message.Sender.UserId != 0 {
		userID = fmt.Sprintf("%d", message.Sender.UserId)
	}

	var chatID string
	switch {
	case message.Recipient.ChatId != 0:
		chatID = fmt.Sprintf("%d", message.Recipient.ChatId)
	case message.Recipient.UserId != 0:
		chatID = fmt.Sprintf("%d", message.Recipient.UserId)
	}

	if userID == "" || chatID == "" {
		return IncomingMessage{}, fmt.Errorf("в MAX update не хватает user_id или chat_id")
	}

	incoming := IncomingMessage{
		Platform:    "max",
		MessageType: detectMessageType(message),
		UserID:      userID,
		ChatID:      chatID,
		Text:        message.Body.Text,
		Metadata:    map[string]any{},
	}

	if message.Timestamp != 0 {
		incoming.Timestamp = formatUnixTimestamp(message.Timestamp)
	}

	incoming.MessageID = message.Body.Mid
	incoming.Metadata["sender_name"] = message.Sender.Name

	return incoming, nil
}

// buildCallbackEvent нормализует MAX callback update к контракту core.
func buildCallbackEvent(update *schemes.MessageCallbackUpdate) (CallbackEvent, error) {
	rawUpdate, err := json.Marshal(update)
	if err != nil {
		return CallbackEvent{}, fmt.Errorf("не удалось сериализовать MAX callback update: %w", err)
	}

	var payload map[string]any
	if err := json.Unmarshal(rawUpdate, &payload); err != nil {
		return CallbackEvent{}, fmt.Errorf("не удалось разобрать MAX callback update: %w", err)
	}

	callbackMap, _ := payload["callback"].(map[string]any)
	messageMap, _ := payload["message"].(map[string]any)
	recipientMap, _ := messageMap["recipient"].(map[string]any)
	bodyMap, _ := messageMap["body"].(map[string]any)
	userMap, _ := callbackMap["user"].(map[string]any)

	userID := extractNumericString(userMap["user_id"])
	chatID := extractNumericString(recipientMap["chat_id"])
	if chatID == "" {
		chatID = extractNumericString(recipientMap["user_id"])
	}

	callbackData := extractString(callbackMap["payload"])
	messageID := extractString(bodyMap["mid"])
	if userID == "" || chatID == "" || callbackData == "" {
		return CallbackEvent{}, fmt.Errorf("в MAX callback update не хватает user_id, chat_id или callback_data")
	}

	return CallbackEvent{
		Platform:     "max",
		UserID:       userID,
		ChatID:       chatID,
		CallbackData: callbackData,
		MessageID:    messageID,
		Metadata: map[string]any{
			"callback_id": callbackMap["callback_id"],
		},
	}, nil
}

// sendFallbackMessage отправляет короткий ответ, если core временно недоступен.
func sendFallbackMessage(
	ctx context.Context,
	api *maxbot.Api,
	update *schemes.MessageCreatedUpdate,
) error {
	var chatID int64
	var userID int64
	switch {
	case update.Message.Recipient.ChatId != 0:
		chatID = update.Message.Recipient.ChatId
	case update.Message.Sender.UserId != 0:
		userID = update.Message.Sender.UserId
	default:
		return fmt.Errorf("некуда отправить fallback-сообщение MAX")
	}

	if err := sendMessage(ctx, api, userID, chatID, "Сервис временно недоступен.", nil); err != nil {
		return fmt.Errorf("не удалось отправить fallback-сообщение MAX: %w", err)
	}

	return nil
}

func sendMessage(
	ctx context.Context,
	api *maxbot.Api,
	userID int64,
	chatID int64,
	text string,
	buttons [][]InlineButton,
) error {
	if text == "" {
		return fmt.Errorf("пустой текст сообщения для отправки")
	}

	message := maxbot.NewMessage()
	message.SetText(text)
	addKeyboardToMessage(message, buttons)

	switch {
	case chatID != 0:
		message.SetChat(chatID)
	case userID != 0:
		message.SetUser(userID)
	default:
		return fmt.Errorf("не указан chat_id или user_id для отправки")
	}

	if err := api.Messages.Send(ctx, message); err != nil {
		return err
	}
	return nil
}

func startInternalServer(ctx context.Context, settings Settings, api *maxbot.Api) *http.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/internal/send", func(writer http.ResponseWriter, request *http.Request) {
		handleInternalSend(writer, request, api)
	})

	server := &http.Server{
		Addr:    ":" + settings.InternalPort,
		Handler: mux,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Printf("ошибка остановки internal MAX server: %v", err)
		}
	}()

	go func() {
		log.Printf("internal MAX server started on :%s", settings.InternalPort)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Printf("ошибка запуска internal MAX server: %v", err)
		}
	}()

	return server
}

func handleInternalSend(
	writer http.ResponseWriter,
	request *http.Request,
	api *maxbot.Api,
) {
	if request.Method != http.MethodPost {
		http.Error(writer, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var payload InternalSendRequest
	if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
		http.Error(writer, "invalid json body", http.StatusBadRequest)
		return
	}

	var userID int64
	var chatID int64
	var err error

	if payload.UserID != "" {
		userID, err = strconv.ParseInt(payload.UserID, 10, 64)
		if err != nil {
			http.Error(writer, "invalid user_id", http.StatusBadRequest)
			return
		}
	}
	if payload.ChatID != "" {
		chatID, err = strconv.ParseInt(payload.ChatID, 10, 64)
		if err != nil {
			http.Error(writer, "invalid chat_id", http.StatusBadRequest)
			return
		}
	}

	if payload.Text == "" {
		http.Error(writer, "text is required", http.StatusBadRequest)
		return
	}

	if err := sendMessage(request.Context(), api, userID, chatID, payload.Text, nil); err != nil {
		http.Error(writer, err.Error(), http.StatusBadGateway)
		return
	}

	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(map[string]any{
		"ok": true,
	})
}

func parseOptionalInt64(value string) (int64, error) {
	if value == "" {
		return 0, nil
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("не удалось преобразовать значение %q в int64: %w", value, err)
	}
	return parsed, nil
}

func extractNumericString(value any) string {
	switch typed := value.(type) {
	case float64:
		return fmt.Sprintf("%.0f", typed)
	case int64:
		return fmt.Sprintf("%d", typed)
	case int:
		return fmt.Sprintf("%d", typed)
	case json.Number:
		return typed.String()
	case string:
		return typed
	default:
		return ""
	}
}

func extractString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	default:
		if typed == nil {
			return ""
		}
		raw, err := json.Marshal(typed)
		if err != nil {
			return ""
		}
		var asString string
		if err := json.Unmarshal(raw, &asString); err == nil {
			return asString
		}
		return string(raw)
	}
}

func valueOrDefault(value string, defaultValue string) string {
	if value == "" {
		return defaultValue
	}
	return value
}

// formatUnixTimestamp нормализует timestamp из MAX в RFC3339.
func formatUnixTimestamp(timestamp int64) string {
	switch {
	case timestamp >= 1_000_000_000_000_000:
		return time.UnixMicro(timestamp).UTC().Format(time.RFC3339)
	case timestamp >= 1_000_000_000_000:
		return time.UnixMilli(timestamp).UTC().Format(time.RFC3339)
	default:
		return time.Unix(timestamp, 0).UTC().Format(time.RFC3339)
	}
}

// detectMessageType определяет платформенно-независимый тип сообщения MAX.
func detectMessageType(message schemes.Message) string {
	if message.Body.Text != "" {
		return "text"
	}
	return "unknown"
}

// addKeyboardToMessage добавляет inline-кнопки к сообщению MAX.
func addKeyboardToMessage(message *maxbot.Message, rows [][]InlineButton) {
	if len(rows) == 0 {
		return
	}

	keyboard := &maxbot.Keyboard{}
	for _, row := range rows {
		if len(row) == 0 {
			continue
		}

		keyboardRow := keyboard.AddRow()
		for _, button := range row {
			keyboardRow.AddCallback(
				button.Text,
				detectButtonIntent(button.CallbackData),
				button.CallbackData,
			)
		}
	}

	message.AddKeyboard(keyboard)
}

// detectButtonIntent подбирает визуальный intent для inline-кнопки.
func detectButtonIntent(callbackData string) schemes.Intent {
	switch callbackData {
	case "feedback:like":
		return schemes.POSITIVE
	case "feedback:dislike":
		return schemes.NEGATIVE
	default:
		return schemes.DEFAULT
	}
}
