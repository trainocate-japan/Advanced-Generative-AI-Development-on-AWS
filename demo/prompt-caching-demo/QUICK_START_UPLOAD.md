# Quick Start: Document Upload Feature

## Overview

The prompt caching demo now supports uploading your own documents to demonstrate caching with custom content!

## How to Use (3 Simple Steps)

### 1. Access the Demo
Open the CloudFront URL provided after deployment

### 2. Upload a Document
- Click **"Choose Document"** button
- Select a .txt or .md file (max 100KB)
- See the file name appear confirming upload

### 3. Ask Questions
- Enter your question about the document
- Click **"Submit Query"**
- Watch the cache performance metrics!

## Try These Sample Documents

We've included three ready-to-use sample documents:

### 📘 prompt-caching-guide.txt (~10,000 tokens)
**Complete guide to Amazon Bedrock prompt caching**

Try asking:
- "What are the best practices for prompt caching?"
- "When should I use prompt caching?"
- "How does prompt caching reduce costs?"

### ☁️ sample-tech-doc.txt (~3,000 tokens)
**Cloud computing best practices**

Try asking:
- "What are the key principles of cloud computing?"
- "How should I design for scalability?"
- "What are cloud security best practices?"

### 🚀 sample-product-guide.txt (~4,000 tokens)
**Product development lifecycle**

Try asking:
- "What are the phases of product development?"
- "How should I conduct user research?"
- "What are common product development pitfalls?"

## What You'll See

After submitting your query, you'll see:

✅ **Document Source**: Shows "📄 Uploaded Document"  
✅ **Token Count**: Estimated tokens in your document  
✅ **Cache Eligibility**: Whether document meets minimum token requirements  
✅ **Performance Metrics**:
   - Token Reduction % (how many tokens saved)
   - Latency Improvement % (how much faster)
   - Cache Hit Ratio % (cache effectiveness)

## Requirements

- **File Format**: .txt or .md files work best
- **File Size**: Maximum 100KB
- **Content Length**: Minimum 100 characters
- **Recommended**: 2,000+ tokens for clear cache benefits

## Tips for Best Results

1. **Use Longer Documents**: Documents with 5,000+ tokens show more dramatic cache benefits
2. **Keep Content Static**: Don't modify the document between requests for consistent cache hits
3. **Ask Multiple Questions**: Submit several questions about the same document to see cache performance
4. **Compare Documents**: Try different document sizes to understand token requirements

## Clear Uploaded Document

Click the **"✕ Clear"** button to remove your uploaded document and return to the default AWS CAF document.

## Educational Value

This feature helps you understand:

- ✅ How document size affects cache eligibility
- ✅ Real-world prompt caching use cases
- ✅ Token reduction and cost savings
- ✅ Latency improvements with caching
- ✅ When caching is most beneficial

## Need Help?

- Check `sample-documents/README.md` for detailed document information
- See `DOCUMENT_UPLOAD_FEATURE.md` for technical details
- Review `INSTRUCTOR_GUIDE.md` for teaching scenarios

## Example Workflow

```
1. Open demo website
2. Click "Choose Document"
3. Select "prompt-caching-guide.txt"
4. Enter question: "What are the best practices for prompt caching?"
5. Click "Submit Query"
6. Observe results:
   - Document: ~10,000 tokens ✓
   - Token Reduction: 85% ✓
   - Latency Improvement: 75% ✓
   - Cache Hit Ratio: 90% ✓
```

## What's Next?

Try creating your own documents:
- Technical documentation
- Code files
- Research papers
- Product specifications
- Training materials

Experiment with different document sizes and content types to understand how prompt caching works in various scenarios!

---

**Happy Caching! 🚀**
