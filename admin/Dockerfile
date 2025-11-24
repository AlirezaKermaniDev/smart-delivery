# admin/Dockerfile

FROM node:20-alpine

WORKDIR /app

# Install deps
COPY package*.json ./
RUN npm install

# Copy source
COPY . .

# Vite dev server env – you can override VITE_API_BASE in docker-compose
ARG VITE_API_BASE
ENV VITE_API_BASE=$VITE_API_BASE

EXPOSE 5173

# Run Vite dev server like frontend
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
