# Sample Documents for Prompt Caching Demo

This folder contains sample documents that you can upload to the prompt caching demo website to experiment with custom content.

## Available Documents

### 1. prompt-caching-guide.txt (~10,000 tokens)
**Comprehensive guide to Amazon Bedrock prompt caching**

This document contains detailed information about prompt caching on Amazon Bedrock, including:
- When to use prompt caching
- How prompt caching works
- Supported models and token requirements
- Implementation examples with Converse API
- Best practices and cost optimization strategies
- Common pitfalls to avoid

**Suggested Questions:**
- "What are the best practices for prompt caching?"
- "When should I use prompt caching?"
- "How does prompt caching work on Amazon Bedrock?"
- "What are the cost benefits of prompt caching?"
- "Which models support prompt caching?"
- "What is the minimum token requirement for caching?"

### 2. sample-tech-doc.txt (~3,000 tokens)
**Cloud computing best practices guide**

This document covers fundamental cloud architecture principles including:
- Designing for scalability
- Implementing security in depth
- Cost optimization strategies
- Building for resilience
- Automation and DevOps practices

**Suggested Questions:**
- "What are the key principles of cloud computing?"
- "How should I design for scalability?"
- "What are the best practices for cloud security?"
- "How can I optimize cloud costs?"
- "What is DevOps culture?"

### 3. sample-product-guide.txt (~4,000 tokens)
**Product development lifecycle guide**

This document outlines the complete product development process:
- Discovery and research phase
- Ideation and concept development
- Design and prototyping
- Development and testing
- Beta testing and validation
- Launch and go-to-market
- Measurement and iteration

**Suggested Questions:**
- "What are the phases of product development?"
- "How should I conduct user research?"
- "What is the best approach to beta testing?"
- "What are common pitfalls in product development?"
- "How do I measure product success?"

### 4. bezos-1997-shareholder-letter.txt (~2,500 tokens)
**Jeff Bezos' 1997 Amazon Shareholder Letter**

This historic document is Amazon's first shareholder letter, outlining the company's long-term philosophy:
- Focus on long-term value over short-term profits
- Customer obsession as core principle
- Investment in market leadership
- Building an enduring franchise
- The famous "Day 1" philosophy

**Suggested Questions:**
- "What is Amazon's long-term investment philosophy?"
- "What does 'Day 1' mean to Amazon?"
- "How does Amazon prioritize customer obsession?"
- "What were Amazon's key metrics in 1997?"
- "What is Amazon's approach to hiring and culture?"
- "How does Amazon make bold investment decisions?"

## How to Use These Documents

1. **Navigate to the Demo Website**: Open the CloudFront URL provided after deployment
2. **Click "Choose Document"**: Located below the question input field
3. **Select a Sample Document**: Choose one of the .txt files from this folder
4. **Enter Your Question**: Ask a question related to the document content
5. **Submit Query**: Click "Submit Query" to see prompt caching in action
6. **Observe Results**: The results will show:
   - Document source as "📄 Uploaded Document"
   - Estimated token count
   - Cache performance metrics (token reduction, latency improvement)

## Token Requirements

For effective prompt caching demonstration:
- **Minimum tokens**: 1,024 tokens (varies by model)
- **Recommended**: 2,000+ tokens for clear cache benefits
- All sample documents meet the minimum requirements

## Creating Your Own Documents

You can create your own documents for testing:

**Requirements:**
- Format: .txt or .md files
- Size: Maximum 100KB
- Content: Minimum 100 characters (recommended 2,000+ tokens)
- Structure: Plain text works best

**Tips:**
- Use documents with repetitive content that would benefit from caching
- Technical documentation, code files, and research papers work well
- Ensure content is static (doesn't change between requests)
- Longer documents (5,000+ tokens) show more dramatic cache benefits

## Educational Value

These sample documents help demonstrate:

1. **Token Requirements**: See how document size affects cache eligibility
2. **Cache Performance**: Compare baseline vs cached request metrics
3. **Real-World Use Cases**: Understand practical applications of prompt caching
4. **Cost Optimization**: Observe token reduction and cost savings
5. **Latency Improvements**: Measure response time improvements

## Additional Resources

- [Amazon Bedrock Prompt Caching Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [AWS Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/)
- [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)

## Feedback

If you create interesting sample documents or have suggestions for additional examples, consider contributing them to help other learners!
