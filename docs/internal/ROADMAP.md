# HTML2MD Development Roadmap

> Historical and superseded. This 2025 planning artifact is not a current
> delivery commitment. Scale-out work is governed by
> [`ADR 0001`](../adr/0001-defer-scale-out-crawling.md) and remains deferred
> until its measured-need, benchmark, architecture, and security gates pass.

## Executive Summary
This roadmap outlines the planned development for html2md, focusing on enterprise-grade features for large-scale, respectful web crawling. The implementation is organized into 4 phases over approximately 4 weeks.

## Vision Statement
Transform html2md from a simple conversion tool into a professional-grade, distributed web crawling system that respects server resources while providing enterprise features like scheduling, persistence, and monitoring.

## Development Phases

### 🏗️ Phase 1: Foundation (Week 1)
**Goal**: Establish solid foundation for advanced features

#### DEPS-001: Fix Dependencies ⏱️ Day 1
- Create comprehensive requirements.txt
- Add development and optional dependencies
- Setup automated dependency testing
- **Deliverable**: Working installation process

#### STATE-001: Progress Persistence 📅 Days 1-3
- Design and implement state management system
- Add checkpointing mechanism
- Create resume capability
- Build state inspection tools
- **Deliverable**: Interruptible and resumable crawls

### 🚀 Phase 2: Core Features (Week 2)
**Goal**: Implement primary enterprise features

#### SCHED-001: Off-Peak Scheduling 📅 Days 4-6
- Implement scheduling engine
- Add timezone support
- Create daemon mode
- System scheduler integration
- **Deliverable**: Time-based crawl automation

#### BATCH-001: Session Batching 📅 Days 4-6 (parallel)
- Design session architecture
- Implement batch processing
- Add cooldown management
- Create session CLI
- **Deliverable**: Large crawl distribution

### 🔧 Phase 3: Enhancements (Week 3)
**Goal**: Add advanced capabilities and monitoring

#### SCHED-002: Advanced Scheduling 📅 Days 7-9
- Holiday detection
- Adaptive scheduling
- Load-based adjustments
- **Deliverable**: Smart scheduling

#### PERF-001: Performance Monitoring 📅 Days 7-9 (parallel)
- Metrics collection
- Performance dashboards
- Resource tracking
- **Deliverable**: Operational visibility

#### CLOUD-001: Cloud Storage 📅 Days 10-12
- S3 integration
- GCS support
- Azure blob storage
- **Deliverable**: Cloud-native storage

#### NOTIF-001: Webhooks 📅 Days 10-11 (parallel)
- Webhook framework
- Event types
- Retry logic
- **Deliverable**: Real-time notifications

### 🌟 Phase 4: Advanced Features (Week 4)
**Goal**: Enable enterprise-scale operations

#### DIST-001: Distributed Crawling 📅 Days 13-17
- Multi-node coordination
- Work distribution
- State synchronization
- **Deliverable**: Horizontal scaling

#### UI-001: Web Dashboard 📅 Days 13-17 (parallel)
- Management interface
- Real-time monitoring
- Configuration UI
- **Deliverable**: User-friendly management

## Milestones & Metrics

### Week 1 Milestone
- ✅ All dependencies resolved
- ✅ Basic persistence working
- ✅ 100% of interrupted crawls resumable

### Week 2 Milestone
- ✅ Scheduled crawls operational
- ✅ Batch processing functional
- ✅ 50% reduction in sustained server load

### Week 3 Milestone
- ✅ Smart scheduling active
- ✅ Performance metrics available
- ✅ Cloud storage integrated
- ✅ Notifications working

### Week 4 Milestone
- ✅ Distributed mode operational
- ✅ Web UI launched
- ✅ Full enterprise feature set

## Technical Architecture

### State Management
```
┌─────────────────┐     ┌──────────────┐
│   Crawler Core  │────▶│ State Manager │
└─────────────────┘     └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │ Checkpointer │
                        └──────┬───────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
         ┌──────▼──────┐              ┌──────▼──────┐
         │ Local Files │              │ Cloud Store │
         └─────────────┘              └─────────────┘
```

### Scheduling System
```
┌─────────────┐     ┌────────────┐     ┌──────────┐
│  Scheduler  │────▶│ Time Rules │────▶│ Executor │
└─────────────┘     └────────────┘     └──────────┘
       │                                      │
       ▼                                      ▼
┌─────────────┐                        ┌──────────┐
│ System Cron │                        │ Crawler  │
└─────────────┘                        └──────────┘
```

## Quality Assurance

### Testing Strategy
- Unit tests for each component
- Integration tests for workflows
- Performance benchmarks
- Load testing for distributed mode

### Documentation Plan
- API documentation
- User guides
- Architecture diagrams
- Migration guides

### Code Quality Standards
- Type hints throughout
- Comprehensive docstrings
- Code coverage > 80%
- Performance profiling

## Risk Mitigation

### Technical Risks
| Risk | Mitigation |
|------|------------|
| State corruption | Atomic writes, backups, validation |
| Scheduling drift | NTP sync, drift detection |
| Distributed coordination | Leader election, consensus protocols |
| Performance regression | Continuous benchmarking |

### Operational Risks
| Risk | Mitigation |
|------|------------|
| Breaking changes | Semantic versioning, migration tools |
| Dependency conflicts | Version pinning, testing matrix |
| Platform differences | CI/CD on multiple platforms |

## Success Metrics

### Performance KPIs
- Checkpoint save time < 100ms
- Resume time < 1 second
- Memory overhead < 10%
- Scheduling accuracy ± 1 minute

### User Experience KPIs
- Setup time < 5 minutes
- Clear error messages
- Intuitive CLI design
- Comprehensive documentation

### Operational KPIs
- 99.9% crawl completion rate
- < 1% server error rate
- Automatic recovery success > 95%

## Future Considerations

### Version 2.0 Ideas
- Machine learning optimization
- Browser automation support
- API-first architecture
- Plugin system
- Multi-language support

### Community Features
- Shared crawl configurations
- Public crawl statistics
- Community modules
- Crawl coordination network

## Communication Plan

### Progress Updates
- Weekly summary in DEVELOPMENT_JOURNAL.md
- Git commits with detailed messages
- GitHub issues for bugs
- Discussions for features

### Documentation Updates
- README.md for quick start
- ARCHITECTURE.md for design
- API.md for developers
- CHANGELOG.md for releases

---

*This roadmap is retained only as historical planning context.*
