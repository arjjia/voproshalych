FROM golang:1.24-alpine AS build
WORKDIR /app
COPY go.mod go.sum main.go ./
RUN go build -o max-bot .

FROM alpine:3.19
COPY --from=build /app/max-bot /usr/local/bin/max-bot
CMD ["max-bot"]
