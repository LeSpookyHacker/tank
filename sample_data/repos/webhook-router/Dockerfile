FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/router ./cmd/router

FROM gcr.io/distroless/static-debian12
USER 10001:10001
COPY --from=build /out/router /router
EXPOSE 9090
ENTRYPOINT ["/router"]
