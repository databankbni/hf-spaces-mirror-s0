#!/bin/bash

# Script to build the React admin panel and deploy it to the docs/admin folder for GitHub Pages.

# Exit on error
set -e

echo "🚀 Starting Admin Panel Deployment..."

# Navigate to admin-panel directory
cd "$(dirname "$0")"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
  echo "📦 Installing dependencies..."
  npm install
fi

# Build the project
echo "🔨 Building the project with Vite..."
npm run build

# Prepare the target directory
TARGET_DIR="../docs/admin"
echo "📂 Preparing target directory: $TARGET_DIR"

if [ -d "$TARGET_DIR" ]; then
  echo "🧹 Cleaning existing files in $TARGET_DIR"
  rm -rf "$TARGET_DIR"
fi

mkdir -p "$TARGET_DIR"

# Copy build output to docs/admin
echo "📤 Copying build files to $TARGET_DIR"
cp -R dist/* "$TARGET_DIR"

# Special fix for GitHub Pages SPA routing (404.html)
echo "📄 Creating 404.html for SPA routing support..."
cp dist/index.html "$TARGET_DIR/404.html"

echo "✅ Admin Panel deployed to docs/admin successfully!"
echo "📍 Access it at: https://moneyplan.pro/admin/"
