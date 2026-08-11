# Instructor Guide: Amazon Bedrock Prompt Caching Demo

This guide provides instructors with educational objectives, teaching tips, common issues and solutions, and cost estimates for running the Amazon Bedrock Prompt Caching demonstration.

## Educational Objectives

### Primary Learning Goals

By the end of this demonstration, students should be able to:

1. **Understand Prompt Caching Fundamentals**
   - Explain what prompt caching is and how it works
   - Identify the cache checkpoint syntax in Bedrock API calls
   - Understand the 5-minute cache TTL (Time To Live)
   - Recognize when caching is beneficial vs when it's not

2. **Analyze Cost Optimization**
   - Calculate cost savings from cache hits (reduced rate, varies by model)
   - Understand the cache write premium (additional cost, varies by model)
   - Determine break-even point for cache effectiveness
   - Evaluate ROI for different usage patterns

3. **Recognize Ideal Use Cases**
   - Document-based Q&A systems
   - Repeated context scenarios (chatbots, assistants)
   - Long system prompts with variable user inputs
   - Multi-turn conversations with persistent context

4. **Apply Best Practices**
   - Structure prompts to maximize cache effectiveness
   - Place cache checkpoints strategically
   - Understand minimum token requirements (1024 tokens)
   - Monitor cache hit ratios and optimize accordingly

### Secondary Learning Goals

Students will also gain exposure to:

- AWS serverless architecture patterns
- Infrastructure as Code with AWS CDK
- API design and integration
- Security best practices (input validation, error sanitization)
- Performance optimization techniques

## Document Upload Feature

### Overview

Students can now upload their own documents to demonstrate prompt caching with custom content. This enhances the learning experience by allowing experimentation with real-world documents.

### How to Use

1. **Access the Upload Feature**: On the demo website, students will see a "Choose Document" button below the question input
2. **Select a Document**: Click the button and select a .txt or .md file (max 100KB)
3. **Submit Query**: Enter a question about the uploaded document and submit
4. **Observe Results**: The results will show "📄 Uploaded Document" as the source

### Sample Documents

Two sample documents are provided in the `sample-documents/` folder:
- `sample-tech-doc.txt`: Cloud computing best practices (~3,000 tokens)
- `sample-product-guide.txt`: Product development lifecycle (~4,000 tokens)

### Teaching Scenarios

**Scenario 1: Token Requirements**
- Have students upload a very small document (< 1,000 tokens)
- Show how the system warns about minimum token requirements
- Discuss why caching requires a minimum document size

**Scenario 2: Custom Content**
- Students upload documents related to their projects or interests
- Demonstrate that caching works with any content type
- Compare cache performance across different document sizes

**Scenario 3: Real-World Use Cases**
- Upload technical documentation, code files, or research papers
- Show how caching benefits document Q&A applications
- Discuss practical applications in their own projects

### Best Practices for Instructors

1. **Prepare Sample Documents**: Have a variety of documents ready for different demonstrations
2. **Explain File Limits**: Clarify the 100KB limit and why it exists (Lambda payload limits)
3. **Show Token Estimation**: Explain how token counts are estimated (word_count * 1.3)
4. **Demonstrate Clearing**: Show how to clear uploaded documents to revert to default
5. **Discuss Security**: Explain that documents are processed in-memory and not stored

## Teaching Tips

### Pre-Session Preparation

**1-2 Days Before**:
- Deploy the demonstration using `./scripts/setup.sh`
- Test the CloudFront URL to ensure it's accessible
- Submit a few test queries to verify functionality
- Review the architecture diagram and prepare explanations
- Prepare example questions that demonstrate cache effectiveness

**Day Of**:
- Have the CloudFront URL ready to share with students
- Open the demo in your browser before class starts
- Have AWS Console open to show CloudWatch logs (optional)
- Prepare backup slides in case of connectivity issues

### Recommended Teaching Flow

#### Part 1: Introduction (10 minutes)

1. **Explain the Problem**:
   - "When using LLMs, we often send the same context repeatedly"
   - "Example: A chatbot that includes company documentation in every request"
   - "This wastes tokens, increases costs, and adds latency"

2. **Introduce the Solution**:
   - "Amazon Bedrock offers prompt caching to address this"
   - "Cache frequently used prompt prefixes for 5 minutes"
   - "Reduced pricing for cached tokens, premium for cache writes (model-specific)"
   - "See AWS Bedrock pricing page for exact rates per model"

3. **Show the Architecture**:
   - Display the architecture diagram from the demo
   - Explain each component's role
   - Highlight where caching occurs (Bedrock API)

#### Part 2: Live Demonstration (15 minutes)

1. **First Query - Baseline**:
   - Submit a question: "What are the key principles of AWS CAF for AI?"
   - Point out the baseline metrics (full token count)
   - Explain that this request processes the entire document

2. **Second Query - Cache Write**:
   - Explain that the system is now writing to cache
   - Show the cache_write_tokens metric
   - Discuss the premium cost for cache writes (varies by model)

3. **Third Query - Cache Hit**:
   - Submit a different question: "How does AWS CAF address governance?"
   - Highlight the dramatic token reduction
   - Show the cache_read_tokens metric
   - Calculate the cost savings together

4. **Compare Results**:
   - Show the side-by-side comparison
   - Discuss token reduction percentage (typically 85-95%)
   - Discuss latency improvement (typically 40-60%)
   - Calculate actual cost savings based on pricing

#### Part 3: Hands-On Practice (20 minutes)

1. **Student Experimentation**:
   - Share the CloudFront URL with students
   - Have them submit their own questions
   - Encourage them to observe the metrics
   - Ask them to calculate cost savings

2. **Discussion Questions**:
   - "When would caching NOT be beneficial?"
   - "How long should content be cached?"
   - "What happens if the document changes?"
   - "How do you determine the break-even point?"

3. **Real-World Scenarios**:
   - Discuss use cases from their projects
   - Identify opportunities for caching
   - Estimate potential cost savings

#### Part 4: Best Practices (10 minutes)

1. **Optimal Cache Checkpoint Placement**:
   - Place after stable, reusable content
   - Place before variable user inputs
   - Ensure cached content exceeds 1024 tokens

2. **Monitoring and Optimization**:
   - Track cache hit ratios
   - Monitor cost savings
   - Adjust cache strategy based on usage patterns

3. **Common Pitfalls**:
   - Caching content that changes frequently
   - Not meeting minimum token requirements
   - Forgetting about the 5-minute TTL
   - Over-optimizing for edge cases

### Interactive Activities

#### Activity 1: Cost Calculation Exercise

**Objective**: Students calculate cost savings from caching

**Instructions**:
1. Provide a scenario: "1000 requests per day, 3000 token document, 200 token questions"
2. Have students calculate:
   - Cost without caching
   - Cost with caching (assume 80% cache hit rate)
   - Total savings per month
3. Discuss results as a class

**Sample Calculation**:
```
Without caching:
- Input tokens per request: 3200 (3000 + 200)
- Total input tokens per day: 3,200,000
- Cost (at $0.003 per 1K tokens): $9.60/day = $288/month

With caching (80% hit rate):
- First request: 3200 tokens + cache write premium (varies by model)
- Cache hits (800 requests): 200 new tokens + cached tokens at reduced rate
- Cache misses (200 requests): 3200 tokens at standard rate
- Total: 4000 + (800 * 500) + (200 * 3200) = 1,044,000 tokens
- Cost: $3.13/day = $93.90/month
- Savings: $194.10/month (67% reduction)
```

#### Activity 2: Use Case Identification

**Objective**: Students identify appropriate use cases for caching

**Instructions**:
1. Present various scenarios
2. Have students determine if caching is appropriate
3. Discuss reasoning as a class

**Scenarios**:
- ✅ Customer support chatbot with company knowledge base
- ✅ Document Q&A system with static documents
- ✅ Code assistant with project context
- ❌ Real-time news summarization (content changes frequently)
- ❌ One-time document analysis (no repeated context)
- ✅ Multi-turn conversation with persistent system prompt

#### Activity 3: Architecture Design

**Objective**: Students design a system using prompt caching

**Instructions**:
1. Provide a use case: "Design a customer support chatbot"
2. Have students:
   - Identify what to cache (knowledge base, system prompt)
   - Determine cache checkpoint placement
   - Estimate token counts and cost savings
   - Consider cache invalidation strategy
3. Present designs to the class

## Common Issues and Solutions

### Issue 1: Cache Not Working

**Symptoms**:
- Token reduction is 0% or minimal
- cache_read_tokens is 0
- No performance improvement

**Possible Causes**:
1. Document is below 1024 token minimum
2. Cache has expired (5-minute TTL)
3. Document content changed between requests
4. Model doesn't support caching

**Solutions**:
- Verify document token count in the UI
- Submit requests within 5 minutes of each other
- Ensure document content is identical
- Check that selected model supports caching

**Teaching Moment**: Use this to discuss cache TTL and minimum requirements

### Issue 2: Deployment Fails

**Symptoms**:
- Setup script exits with error
- CloudFormation stack creation fails
- Resources partially created

**Possible Causes**:
1. AWS credentials not configured
2. Insufficient permissions
3. Service quotas exceeded
4. Region doesn't support Bedrock

**Solutions**:
- Run `aws configure` to set credentials
- Verify IAM permissions include required services
- Request quota increases if needed
- Deploy to a Bedrock-supported region (us-east-1, us-west-2)

**Teaching Moment**: Discuss AWS permissions and service availability

### Issue 3: High Costs

**Symptoms**:
- AWS bill higher than expected
- Many Bedrock API calls

**Possible Causes**:
1. Teardown script not run after session
2. Students making excessive requests
3. Using expensive models

**Solutions**:
- Always run `./scripts/teardown.sh` after each session
- Implement rate limiting (already configured)
- Use cost-effective models (Amazon Nova Lite)
- Monitor costs in AWS Cost Explorer

**Teaching Moment**: Discuss cost management and cleanup importance

### Issue 4: Website Not Loading

**Symptoms**:
- CloudFront URL returns 403 or 404
- Blank page or error message

**Possible Causes**:
1. CloudFront distribution still deploying
2. Website files not uploaded to S3
3. Browser caching old version

**Solutions**:
- Wait 2-3 minutes for CloudFront deployment
- Verify files in S3 bucket via AWS Console
- Hard refresh browser (Ctrl+F5 or Cmd+Shift+R)
- Check CloudFront distribution status

**Teaching Moment**: Discuss CDN propagation and caching

### Issue 5: API Errors

**Symptoms**:
- "Failed to connect to API" error
- 500 Internal Server Error
- Timeout errors

**Possible Causes**:
1. Lambda function error
2. Bedrock API throttling
3. Network connectivity issues
4. Invalid model ID

**Solutions**:
- Check CloudWatch logs for Lambda errors
- Verify Bedrock model access in console
- Test API Gateway health endpoint
- Ensure model ID is correct

**Teaching Moment**: Discuss error handling and debugging strategies

### Issue 6: Inconsistent Results

**Symptoms**:
- Different answers to same question
- Varying token counts
- Unpredictable cache behavior

**Possible Causes**:
1. LLM non-determinism (temperature > 0)
2. Cache expiration between requests
3. Different document versions

**Solutions**:
- Explain that LLMs are probabilistic
- Submit requests close together (within 5 minutes)
- Verify document content hasn't changed

**Teaching Moment**: Discuss LLM behavior and prompt engineering

## Cost Estimates

### Per-Session Costs

**Typical Demo Session** (1 hour, 20 students, 5 queries each):

| Service | Usage | Cost |
|---------|-------|------|
| Amazon Bedrock | 100 queries, ~300K tokens | $0.90 - $3.00 |
| Lambda | 300 invocations, 30 seconds each | $0.05 |
| API Gateway | 300 requests | $0.01 |
| S3 | 300 GET requests | < $0.01 |
| CloudFront | 100 MB data transfer | $0.01 |
| **Total** | | **$1.00 - $3.10** |

**Cost Breakdown by Model**:
- **Amazon Nova Lite**: ~$0.90 per session (most cost-effective)
- **Amazon Nova Pro**: ~$1.50 per session
- **Claude 3.5 Sonnet**: ~$3.00 per session
- **Claude 3 Haiku**: ~$1.20 per session

### Monthly Costs (If Left Running)

**Infrastructure Costs** (no active usage):

| Service | Monthly Cost |
|---------|--------------|
| S3 Storage (1 GB) | $0.02 |
| CloudFront (minimal traffic) | $0.01 |
| Lambda | $0.00 (pay per invocation) |
| API Gateway | $0.00 (pay per request) |
| **Total** | **$0.03** |

**Important**: Always run teardown script after sessions to avoid unnecessary charges.

### Cost Optimization Tips

1. **Use Cost-Effective Models**:
   - Default to Amazon Nova Lite ($0.00006 per 1K input tokens)
   - Reserve expensive models for specific demonstrations

2. **Limit Session Duration**:
   - Run focused 1-hour sessions
   - Teardown immediately after

3. **Set Rate Limits**:
   - Already configured: 10 requests per minute per IP
   - Prevents runaway costs from errors

4. **Monitor Costs**:
   - Check AWS Cost Explorer daily during active use
   - Set up billing alerts for unexpected charges

5. **Batch Sessions**:
   - Run multiple classes in same day
   - Deploy once, use multiple times, teardown at end

### Budget Planning

**Recommended Budget**:
- **Single Session**: $5 (includes buffer)
- **Weekly Course (4 sessions)**: $20
- **Semester (12 sessions)**: $60

**Cost Per Student**:
- 20 students per session: $0.05 - $0.15 per student
- Very cost-effective for educational purposes

## Assessment Ideas

### Formative Assessment

**During Demo**:
- Ask students to predict token reduction before revealing results
- Have students calculate cost savings in real-time
- Poll students on when caching would be beneficial

**Quick Checks**:
- "What's the minimum token requirement for caching?" (1024)
- "How long does cache last?" (5 minutes)
- "What's the cache read discount?" (90%)

### Summative Assessment

**Quiz Questions**:
1. Explain how prompt caching reduces costs in Amazon Bedrock
2. Calculate cost savings for a given scenario
3. Identify appropriate use cases for prompt caching
4. Design a system architecture using prompt caching

**Project Ideas**:
1. Build a document Q&A system with caching
2. Implement a chatbot with cached knowledge base
3. Optimize an existing LLM application with caching
4. Analyze cache hit ratios and cost savings (refer to AWS pricing for calculations)

**Lab Assignment**:
- Deploy the demo in their own AWS account
- Submit 10 queries and analyze results
- Write a report on cost savings and performance
- Propose a real-world use case for their organization

## Additional Teaching Resources

### Recommended Reading

- **AWS Documentation**: [Prompt Caching in Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- **AWS Blog**: Search for "Bedrock prompt caching" for latest articles
- **Cost Optimization**: AWS Well-Architected Framework - Cost Optimization Pillar

### Video Resources

- AWS re:Invent sessions on Amazon Bedrock
- AWS Skill Builder courses on generative AI
- YouTube tutorials on prompt engineering

### Hands-On Labs

- AWS Workshops: Bedrock and generative AI labs
- AWS Skill Builder: Bedrock learning paths
- This demo itself serves as a hands-on lab

## Troubleshooting for Instructors

### Pre-Session Checklist

- [ ] AWS credentials configured and tested
- [ ] Bedrock model access granted
- [ ] Demo deployed successfully
- [ ] CloudFront URL accessible
- [ ] Test queries submitted and working
- [ ] Backup slides prepared
- [ ] Cost alerts configured

### During Session

**If Demo Goes Down**:
1. Switch to backup slides
2. Show pre-recorded screenshots
3. Explain concepts without live demo
4. Schedule makeup session if needed

**If Students Can't Access**:
1. Verify CloudFront URL is correct
2. Check for network/firewall issues
3. Have students try different browsers
4. Use screen sharing as fallback

**If Costs Spike**:
1. Check CloudWatch metrics for unusual activity
2. Verify rate limiting is working
3. Consider pausing demo temporarily
4. Run teardown if necessary

### Post-Session

- [ ] Run teardown script
- [ ] Verify all resources deleted
- [ ] Check AWS bill for session costs
- [ ] Collect student feedback
- [ ] Document any issues encountered
- [ ] Update this guide with lessons learned

## Feedback and Improvement

### Collecting Student Feedback

**Questions to Ask**:
1. Was the demo helpful in understanding prompt caching?
2. Were the cost calculations clear?
3. What additional features would be useful?
4. Did you encounter any technical issues?
5. Would you use prompt caching in your projects?

### Continuous Improvement

**Track Metrics**:
- Student engagement during demo
- Quiz scores on caching concepts
- Number of technical issues
- Session costs vs budget
- Student feedback ratings

**Iterate**:
- Update demo based on feedback
- Add new features or examples
- Improve documentation
- Optimize costs
- Enhance educational content

## Support and Resources

### Getting Help

**Technical Issues**:
1. Check CloudWatch logs for errors
2. Review AWS service health dashboard
3. Consult AWS documentation
4. Contact AWS support if needed

**Educational Questions**:
1. Review this instructor guide
2. Consult AWS training resources
3. Join AWS educator communities
4. Attend AWS education webinars

### Community

- **AWS Educate**: Resources for educators
- **AWS Academy**: Curriculum and support
- **AWS User Groups**: Local communities
- **Online Forums**: AWS re:Post, Stack Overflow

## Conclusion

This demonstration provides an effective, hands-on way to teach Amazon Bedrock prompt caching concepts. By following this guide, instructors can deliver engaging sessions that help students understand cost optimization and performance improvement techniques for generative AI applications.

Remember:
- Always run teardown after sessions
- Monitor costs during active use
- Collect feedback for improvement
- Share lessons learned with other instructors

**Happy Teaching!** 🎓

---

For questions or suggestions about this guide, please provide feedback through your organization's channels.
