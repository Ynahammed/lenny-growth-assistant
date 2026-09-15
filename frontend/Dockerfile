# Lenny Growth Assistant — frontend (Vite dev server with API proxy)
FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Dev proxy target: in Compose this points at the backend service.
ENV BACKEND_ORIGIN=http://backend:8001

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
