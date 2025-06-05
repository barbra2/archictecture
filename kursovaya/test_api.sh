#!/bin/bash

echo "=== Тестирование микросервисного приложения ==="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для проверки статуса ответа
check_status() {
    if [ $1 -eq 200 ] || [ $1 -eq 201 ]; then
        echo -e "${GREEN}✓ Успешно (HTTP $1)${NC}"
    else
        echo -e "${RED}✗ Ошибка (HTTP $1)${NC}"
    fi
}

# Функция для ожидания запуска сервисов
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo "Ожидание запуска $service_name..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s $url > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $service_name запущен${NC}"
            return 0
        fi
        echo "Попытка $attempt/$max_attempts..."
        sleep 2
        ((attempt++))
    done
    
    echo -e "${RED}✗ $service_name не запустился${NC}"
    return 1
}

echo -e "${YELLOW}1. Проверка здоровья сервисов${NC}"

# Ждем запуска сервисов
wait_for_service "http://localhost:8001/health" "API Service"
wait_for_service "http://localhost:8002/health" "CQRS Service"
wait_for_service "http://localhost:8003/health" "Query Service"

# Проверка health endpoints
echo "Проверка API Service..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health)
check_status $status

echo "Проверка CQRS Service..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/health)
check_status $status

echo "Проверка Query Service..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/health)
check_status $status

echo -e "\n${YELLOW}2. Тестирование API Service${NC}"

# Создание книги через API Service
echo "Создание книги через API Service..."
response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
  -X POST "http://localhost:8001/books" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Война и мир",
    "description": "Роман-эпопея Льва Толстого",
    "author": "Лев Толстой"
  }')

status=$(echo $response | tr -d '\n' | sed -e 's/.*HTTPSTATUS://')
body=$(echo $response | sed -e 's/HTTPSTATUS:.*//g')
check_status $status

if [ $status -eq 201 ]; then
    book_id=$(echo $body | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
    echo "ID созданной книги: $book_id"
fi

# Получение всех книг
echo "Получение всех книг..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/books)
check_status $status

# Поиск книги по названию
echo "Поиск книги по названию 'Война'..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/books/search/Война)
check_status $status

echo -e "\n${YELLOW}3. Тестирование CQRS Service${NC}"

# Создание книги через CQRS
book_uuid=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
echo "Создание книги через CQRS (UUID: $book_uuid)..."

status=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:8002/commands/create-book" \
  -H "Content-Type: application/json" \
  -d "{
    \"aggregate_id\": \"$book_uuid\",
    \"title\": \"Преступление и наказание\",
    \"description\": \"Роман Федора Достоевского\",
    \"author\": \"Федор Достоевский\"
  }")
check_status $status

# Получение событий агрегата
echo "Получение событий агрегата..."
sleep 2  # Ждем обработки команды
status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8002/events/$book_uuid")
check_status $status

# Получение агрегата
echo "Получение агрегата..."
status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8002/aggregates/$book_uuid")
check_status $status

echo -e "\n${YELLOW}4. Тестирование Query Service${NC}"

# Ждем проекции событий
sleep 3

# Получение всех книг из Read Models
echo "Получение всех книг из Read Models..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/books)
check_status $status

# Поиск книг по автору
echo "Поиск книг по автору 'Достоевский'..."
status=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:8003/books/search" \
  -H "Content-Type: application/json" \
  -d '{
    "author": "Достоевский"
  }')
check_status $status

# Получение статистики
echo "Получение статистики..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/statistics)
check_status $status

# Получение списка авторов
echo "Получение списка авторов..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/authors)
check_status $status

echo -e "\n${YELLOW}5. Проверка мониторинга${NC}"

# Проверка Prometheus
echo "Проверка Prometheus..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9091)
check_status $status

# Проверка Grafana
echo "Проверка Grafana..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3004)
check_status $status

# Проверка метрик сервисов
echo "Проверка метрик API Service..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/metrics)
check_status $status

echo "Проверка метрик CQRS Service..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/metrics)
check_status $status

echo "Проверка метрик Query Service..."
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/metrics)
check_status $status

echo -e "\n${GREEN}=== Тестирование завершено ===${NC}"
echo -e "${YELLOW}Доступные интерфейсы:${NC}"
echo "- API Service Swagger: http://localhost:8001/docs"
echo "- CQRS Service Swagger: http://localhost:8002/docs"
echo "- Query Service Swagger: http://localhost:8003/docs"
echo "- Grafana: http://localhost:3004 (admin/admin)"
echo "- Prometheus: http://localhost:9091"
echo "- RabbitMQ Management: http://localhost:15673 (guest/guest)"
