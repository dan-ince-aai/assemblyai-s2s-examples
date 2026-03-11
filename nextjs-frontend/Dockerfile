FROM node:22-alpine
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Build Next.js and compile server.ts → server.js
RUN npm run build && \
    npx tsc server.ts \
      --esModuleInterop --module commonjs --target es2020 \
      --lib es2020 --skipLibCheck --outDir .

EXPOSE 3000
ENV NODE_ENV=production
ENV PORT=3000

CMD ["node", "server.js"]
