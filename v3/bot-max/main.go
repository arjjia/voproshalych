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
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"

	maxbot "github.com/max-messenger/max-bot-api-client-go"
	"github.com/max-messenger/max-bot-api-client-go/schemes"
)

type Settings struct {
	MaxBotToken               string
	BotCoreURL                string
	BotCoreTimeoutSeconds     time.Duration
	InternalPort              string
	RequestDelayAfterFailures time.Duration
}

type AgentRequest struct {
	Query string `json:"query"`
}

type AgentResponse struct {
	Answer string `json:"answer"`
}

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

type InternalSendRequest struct {
	UserID string `json:"user_id,omitempty"`
	ChatID string `json:"chat_id,omitempty"`
	Text   string `json:"text"`
}

type AgentClient struct {
	baseURL string
	client  *http.Client
}

func NewSettings() Settings {
	timeoutSeconds := 10 * time.Second
	if rawTimeout := os.Getenv("BOT_CORE_TIMEOUT_SECONDS"); rawTimeout != "" {
		if parsedTimeout, err := time.ParseDuration(rawTimeout + "s"); err == nil {
			timeoutSeconds = parsedTimeout
		}
	}

	return Settings{
		MaxBotToken:               os.Getenv("MAX_BOT_TOKEN"),
		BotCoreURL:                valueOrDefault(os.Getenv("BOT_CORE_URL"), "http://agent-service:8001"),
		BotCoreTimeoutSeconds:     timeoutSeconds,
		InternalPort:              valueOrDefault(os.Getenv("MAX_BOT_INTERNAL_PORT"), "8081"),
		RequestDelayAfterFailures: 2 * time.Second,
	}
}

func NewAgentClient(settings Settings) *AgentClient {
	return &AgentClient{
		baseURL: settings.BotCoreURL,
		client: &http.Client{
			Timeout: settings.BotCoreTimeoutSeconds,
		},
	}
}

func (c *AgentClient) ProcessMessage(ctx context.Context, incomingMsg IncomingMessage) (AgentResponse, error) {
	payload := AgentRequest{Query: incomingMsg.Text}
	body, err := json.Marshal(payload)
	if err != nil {
		return AgentResponse{}, fmt.Errorf("не удалось сериализовать запрос в agent: %w", err)
	}

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+"/chat",
		bytes.NewReader(body),
	)
	if err != nil {
		return AgentResponse{}, fmt.Errorf("не удалось создать запрос в agent: %w", err)
	}

	request.Header.Set("Content-Type", "application/json")

	response, err := c.client.Do(request)
	if err != nil {
		return AgentResponse{}, fmt.Errorf("не удалось отправить запрос в agent: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode >= http.StatusBadRequest {
		responseBody, _ := io.ReadAll(response.Body)
		return AgentResponse{}, fmt.Errorf(
			"agent вернул статус %d: %s",
			response.StatusCode,
			string(responseBody),
		)
	}

	var agentResponse AgentResponse
	if err := json.NewDecoder(response.Body).Decode(&agentResponse); err != nil {
		return AgentResponse{}, fmt.Errorf("не удалось разобрать ответ agent: %w", err)
	}

	return agentResponse, nil
}

func main() {
	settings := NewSettings()
	for settings.MaxBotToken == "" {
		log.Println("MAX_BOT_TOKEN is not set — retrying in 30s...")
		time.Sleep(30 * time.Second)
		settings = NewSettings()
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()

	api, err := maxbot.New(settings.MaxBotToken)
	if err != nil {
		log.Fatalf("не удалось создать MAX API клиент: %v", err)
	}

	agentClient := NewAgentClient(settings)

	server := startInternalServer(ctx, settings, api)
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Printf("ошибка остановки internal MAX server: %v", err)
		}
	}()

	for update := range api.GetUpdates(ctx) {
		if err := handleUpdate(ctx, api, agentClient, update); err != nil {
			log.Printf("ошибка обработки MAX update: %v", err)
			time.Sleep(settings.RequestDelayAfterFailures)
		}
	}
}

func handleUpdate(
	ctx context.Context,
	api *maxbot.Api,
	agentClient *AgentClient,
	update any,
) error {
	messageUpdate, ok := update.(*schemes.MessageCreatedUpdate)
	if !ok {
		return nil
	}

	payload, err := buildIncomingMessage(messageUpdate)
	if err != nil {
		return err
	}

	if shouldShowPendingMessage(payload) {
		var chatID int64
		var userID int64
		switch {
		case messageUpdate.Message.Recipient.ChatId != 0:
			chatID = messageUpdate.Message.Recipient.ChatId
		case messageUpdate.Message.Sender.UserId != 0:
			userID = messageUpdate.Message.Sender.UserId
		}

		if userID != 0 || chatID != 0 {
			_ = sendMessage(ctx, api, userID, chatID,
				"Сейчас я попробую ответить на этот вопрос, это может занять какое-то время...",
				nil,
			)
		}
	}

	response, err := agentClient.ProcessMessage(ctx, payload)
	if err != nil {
		if sendErr := sendFallbackMessage(ctx, api, messageUpdate); sendErr != nil {
			return errors.Join(err, sendErr)
		}
		return err
	}

	text := response.Answer
	if text == "" {
		return nil
	}

	text = stripHTMLToPlain(text)

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

	if err := sendMessage(ctx, api, userID, chatID, text, nil); err != nil {
		return fmt.Errorf("не удалось отправить ответ в MAX: %w", err)
	}

	return nil
}

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

func valueOrDefault(value string, defaultValue string) string {
	if value == "" {
		return defaultValue
	}
	return value
}

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

func detectMessageType(message schemes.Message) string {
	if message.Body.Text != "" {
		return "text"
	}
	return "unknown"
}

type InlineButton struct {
	Text         string `json:"text"`
	CallbackData string `json:"callback_data"`
	URL          string `json:"url,omitempty"`
}

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
			if button.URL != "" {
				keyboardRow.AddLink(
					button.Text,
					schemes.DEFAULT,
					button.URL,
				)
			} else {
				keyboardRow.AddCallback(
					button.Text,
					detectButtonIntent(button.CallbackData),
					button.CallbackData,
				)
			}
		}
	}

	message.AddKeyboard(keyboard)
}

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

func shouldShowPendingMessage(msg IncomingMessage) bool {
	if msg.MessageType != "text" {
		return false
	}

	normalized := strings.TrimSpace(strings.ToLower(msg.Text))
	excluded := map[string]bool{
		"/start":          true,
		"start":           true,
		"начать":          true,
		"📋 помощь":       true,
		"🔄 новый диалог": true,
		"🔔 рассылка":     true,
	}

	return !excluded[normalized]
}

func stripHTMLToPlain(text string) string {
	linkRegex := regexp.MustCompile(`<a href="([^"]+)">([^<]+)</a>`)
	text = linkRegex.ReplaceAllString(text, "$2\n— $1")
	return text
}

func convertReplyToInline(rows [][]ReplyKeyboardButton) [][]InlineButton {
	buttonMapping := map[string]string{
		"📋 Помощь":      "menu:help",
		"🔄 Новый диалог": "menu:new_dialog",
		"🔔 Рассылка":    "menu:subscription",
	}

	var result [][]InlineButton
	for _, row := range rows {
		var buttonRow []InlineButton
		for _, btn := range row {
			callbackData := btn.Text
			if mapped, ok := buttonMapping[btn.Text]; ok {
				callbackData = mapped
			}
			buttonRow = append(buttonRow, InlineButton{
				Text:         btn.Text,
				CallbackData: callbackData,
			})
		}
		result = append(result, buttonRow)
	}
	return result
}

type ReplyKeyboardButton struct {
	Text string `json:"text"`
}
