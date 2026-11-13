FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
ARG VITE_API_PROXY=http://backend:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV API_UPSTREAM=${VITE_API_PROXY}
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
